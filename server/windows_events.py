"""
Crashes and stability events, read from the Windows event logs.

Windows records every unexpected shutdown, blue screen, app crash and
hardware error. Matrix reads the last 30 days (read-only, no admin needed)
when it starts and every 10 minutes, so after a crash you see what happened
as soon as Matrix is back up.

  System log   41 (Kernel-Power)      restarted without shutting down cleanly
               6008 (EventLog)        "the previous shutdown was unexpected"
               1001 (WER-SystemErrorReporting)  blue screen, with its stop code
               WHEA-Logger            hardware errors reported by CPU, memory or PCIe devices
  Application  1000 Application Error / 1002 Application Hang
"""

import base64
import json
import re
from collections import defaultdict
from datetime import datetime

import collectors as c
import repairs
from periodic import PeriodicMonitor

CHECK_EVERY_SECONDS = 600

EVENTS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$since = (Get-Date).AddDays(-30)
function Pack($events) {
  @($events | ForEach-Object {
    $m = ([string]$_.Message) -replace '\s+', ' '
    [ordered]@{ time = $_.TimeCreated.ToString('o'); id = $_.Id; provider = "$($_.ProviderName)";
                message = $m.Substring(0, [Math]::Min(500, $m.Length)) }
  })
}
$r = [ordered]@{}
$r.system   = Pack (Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41, 6008, 1001; StartTime = $since } -MaxEvents 60)
$r.hardware = Pack (Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WHEA-Logger'; StartTime = $since } -MaxEvents 30)
$r.apps     = Pack (Get-WinEvent -FilterHashtable @{ LogName = 'Application'; ProviderName = 'Application Error', 'Application Hang'; StartTime = (Get-Date).AddDays(-14) } -MaxEvents 150)
$r.minidumps = @(Get-ChildItem "$env:SystemRoot\Minidump\*.dmp" | Sort-Object LastWriteTime -Descending | Select-Object -First 10 |
  ForEach-Object { [ordered]@{ name = $_.Name; time = $_.LastWriteTime.ToString('o') } })
$r.memdiag = Pack (Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-MemoryDiagnostics-Results' } -MaxEvents 3)
$r.lastBoot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')
$r | ConvertTo-Json -Depth 4 -Compress
"""

# Common blue-screen stop codes: name and a plain-language first step.
STOP_CODES = {
    0x0000000A: ("IRQL_NOT_LESS_OR_EQUAL", "A driver accessed memory it shouldn't. Usually a driver problem: update graphics, Wi-Fi and chipset drivers."),
    0x0000001A: ("MEMORY_MANAGEMENT", "Often faulty or unstable RAM, sometimes a driver. Run Windows Memory Diagnostic and remove any memory overclock (XMP/EXPO)."),
    0x0000001E: ("KMODE_EXCEPTION_NOT_HANDLED", "A driver crashed. Update drivers, especially recently installed ones."),
    0x0000003B: ("SYSTEM_SERVICE_EXCEPTION", "A driver or system service failed. Update graphics drivers and install pending Windows updates."),
    0x00000050: ("PAGE_FAULT_IN_NONPAGED_AREA", "Bad memory access, by faulty RAM or a driver. Check recent driver installs and test the RAM."),
    0x0000007E: ("SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", "A system driver crashed. Update drivers; the minidump names the culprit."),
    0x0000009F: ("DRIVER_POWER_STATE_FAILURE", "A driver mishandled sleep or wake. Update Wi-Fi, graphics and chipset drivers, and the BIOS."),
    0x000000C5: ("DRIVER_CORRUPTED_EXPOOL", "A driver corrupted system memory. Update or remove recently added drivers."),
    0x000000D1: ("DRIVER_IRQL_NOT_LESS_OR_EQUAL", "A driver accessed memory it shouldn't; network drivers are common culprits. Update them."),
    0x000000EF: ("CRITICAL_PROCESS_DIED", "An essential Windows process stopped. Run `sfc /scannow` in an administrator terminal."),
    0x00000116: ("VIDEO_TDR_FAILURE", "The graphics driver stopped responding. Update the NVIDIA driver and check GPU temperatures; remove any GPU overclock."),
    0x00000124: ("WHEA_UNCORRECTABLE_ERROR", "The hardware itself reported a fatal error (CPU, memory or power). Remove overclocks, update the BIOS and watch temperatures."),
    0x00000133: ("DPC_WATCHDOG_VIOLATION", "A driver took too long to respond; storage and chipset drivers are common. Update them and the SSD firmware."),
    0x00000139: ("KERNEL_SECURITY_CHECK_FAILURE", "Windows detected corrupted data structures, usually from a driver. Update drivers and run `sfc /scannow`."),
    0x00000019: ("BAD_POOL_HEADER", "Memory corruption, usually from a driver. Update or remove recently installed drivers."),
}


# Windows programs that host or run other code. A single crash of one of these
# is usually a symptom of something else (an add-on, a driver), not a problem in itself.
HELPER_PROCESSES = {
    "dllhost.exe": "COM Surrogate: runs other programs' add-ons (thumbnails, codecs, shell extensions) in a separate box so their crashes don't take Explorer down.",
    "svchost.exe": "Service Host: runs Windows services. The faulting module shows which service or driver was involved.",
    "runtimebroker.exe": "Runtime Broker: checks permissions for Store apps.",
    "searchhost.exe": "Windows Search box and results.",
    "searchapp.exe": "Windows Search box and results.",
    "searchui.exe": "Windows Search box and results.",
    "explorer.exe": "File Explorer, the taskbar and the desktop. Often crashed by third-party add-ons (right-click menu items, cloud-drive icons).",
    "startmenuexperiencehost.exe": "The Start menu.",
    "shellexperiencehost.exe": "Windows shell pieces: notifications, the clock and calendar flyouts.",
    "textinputhost.exe": "The touch keyboard, emoji picker and handwriting.",
    "wmiprvse.exe": "WMI Provider Host: answers system-information requests from programs (including Matrix).",
    "backgroundtaskhost.exe": "Runs Store apps' background tasks.",
    "systemsettings.exe": "The Settings app.",
    "sihost.exe": "Shell Infrastructure Host: parts of the desktop and Action Center.",
    "audiodg.exe": "Windows audio engine. Crashes usually come from audio enhancements or drivers.",
    "conhost.exe": "Console Window Host: the frame around command-line windows.",
    "msedgewebview2.exe": "WebView2: a built-in browser engine many apps use for their windows.",
}

# Faulting module -> who it belongs to. Checked as lowercase prefixes/substrings.
MODULE_OWNERS = [
    (("nvwgf2um", "nvd3dum", "nvoglv", "nvcuda", "nvapi", "nvlddmkm", "nvgpucomp"), "NVIDIA graphics driver"),
    (("atiumd", "atio6", "amdxx", "amdihk", "aticfx", "amdenc"), "AMD graphics driver"),
    (("igd", "igc64", "igxelpicd"), "Intel graphics driver"),
    (("d3d11", "d3d12", "dxgi", "d3d9", "dxcore"), "DirectX (Windows graphics), usually a driver or game issue"),
    (("msmpeg2vdec", "mfplat", "mfreadwrite", "msvproc", "mfmp4src"), "Windows video playback (Media Foundation), often a damaged video file"),
    (("lav", "ffmpeg", "avcodec", "icaros", "k-lite", "codec"), "A third-party video codec or thumbnail add-on"),
    (("windows.storage", "shell32", "explorerframe", "thumbcache", "windowscodecs"), "Windows Explorer shell, often a thumbnail or right-click add-on"),
    (("coreclr", "clr.dll", "clrjit", "kernelbase.dll"), "The app's own code (a .NET or general error); updating or reinstalling the app is the usual fix"),
    (("ucrtbase", "msvcp", "vcruntime"), "Microsoft C++ runtime, used by the app; reinstalling the app or the Visual C++ Redistributable often fixes it"),
    (("ntdll.dll",), "Windows core library; too general to point at a cause on its own"),
    (("unknown",), "Unknown module; Windows couldn't tell which code crashed"),
]


def module_owner(module):
    name = module.lower()
    for prefixes, owner in MODULE_OWNERS:
        if any(p in name for p in prefixes):
            return owner
    return None


def parse_time(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_events(raw):
    """Turn raw event-log rows into crashes, hardware errors and crashing apps."""
    system = sorted(raw.get("system") or [], key=lambda e: e["time"])
    bugchecks = [e for e in system if e["id"] == 1001 and "SystemErrorReporting" in e["provider"]]
    crashes = []

    for event in system:
        when = parse_time(event["time"])
        if not when:
            continue
        if event["id"] == 1001 and "SystemErrorReporting" in event["provider"]:
            match = re.search(r"bugcheck was:?\s*(0x[0-9a-fA-F]+)", event["message"], re.IGNORECASE)
            code = int(match.group(1), 16) if match else None
            name, advice = STOP_CODES.get(code, (None, "Windows saved crash details (a minidump). Search the stop code for known causes."))
            crashes.append({
                "time": event["time"], "kind": "bluescreen",
                "title": f"Blue screen: {name}" if name else "Blue screen",
                "code": f"0x{code:08X}" if code is not None else None, "advice": advice,
            })
        elif event["id"] in (41, 6008):
            # Skip if a blue screen is already recorded for the same restart.
            if any(abs((parse_time(b["time"]) - when).total_seconds()) < 900 for b in bugchecks if parse_time(b["time"])):
                continue
            if any(cr["kind"] == "unexpected" and abs((parse_time(cr["time"]) - when).total_seconds()) < 900 for cr in crashes):
                continue
            crashes.append({
                "time": event["time"], "kind": "unexpected",
                "title": "Unexpected shutdown or restart", "code": None,
                "advice": "Windows didn't shut down cleanly: a freeze, holding the power button, the battery "
                          "running flat, or a crash too sudden to record. If it repeats, check temperatures and power settings.",
            })
    crashes.sort(key=lambda cr: cr["time"], reverse=True)

    hardware = []
    for e in raw.get("hardware") or []:
        text = e["message"].lower()
        fatal = "fatal" in text
        corrected = "corrected" in text and not fatal
        hardware.append({
            "time": e["time"],
            "title": "Hardware error (fatal)" if fatal else "Corrected hardware error" if corrected else "Hardware error reported",
            "detail": e["message"][:240],
            "fatal": fatal,
            "corrected": corrected,
        })

    apps = defaultdict(lambda: {"crashes": 0, "hangs": 0, "last": "", "modules": defaultdict(int)})
    for e in raw.get("apps") or []:
        if e["id"] == 1000:
            m = re.search(r"Faulting application name:\s*([^,]+)", e["message"])
            key = "crashes"
        elif e["id"] == 1002:
            m = re.search(r"The program (\S+)", e["message"])
            key = "hangs"
        else:
            continue
        if not m:
            continue
        name = m.group(1).strip()
        apps[name][key] += 1
        apps[name]["last"] = max(apps[name]["last"], e["time"])
        module = re.search(r"Faulting module name:\s*([^,]+)", e["message"])
        if module:
            apps[name]["modules"][module.group(1).strip()] += 1

    app_list = []
    for name, info in apps.items():
        modules = sorted(info["modules"].items(), key=lambda kv: kv[1], reverse=True)
        top = modules[0][0] if modules else None
        helper = HELPER_PROCESSES.get(name.lower())
        app_list.append({
            "name": name, "crashes": info["crashes"], "hangs": info["hangs"], "last": info["last"],
            "module": top, "moduleOwner": module_owner(top) if top else None,
            "helper": helper,
        })
    app_list.sort(key=lambda a: (a["crashes"] + a["hangs"], a["last"]), reverse=True)

    memdiag = None
    for e in raw.get("memdiag") or []:
        text = e["message"].lower()
        memdiag = {"time": e["time"], "ok": "no errors" in text, "detail": e["message"][:200]}
        break

    return {
        "crashes": crashes[:20],
        "hardware": hardware[:10],
        "apps": app_list[:15],
        "minidumps": raw.get("minidumps") or [],
        "memdiag": memdiag,
        "lastBoot": raw.get("lastBoot"),
    }


def run_events_script():
    encoded = base64.b64encode(EVENTS_SCRIPT.encode("utf-16-le")).decode("ascii")
    output = c.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=90)
    start = output.find("{")
    if start < 0:
        return None
    try:
        raw = json.loads(output[start:])
    except json.JSONDecodeError:
        return None
    for key in ("system", "hardware", "apps", "minidumps", "memdiag"):  # single items arrive unwrapped
        if isinstance(raw.get(key), dict):
            raw[key] = [raw[key]]
    return raw


class EventsMonitor(PeriodicMonitor):
    name = "Crash and event log"
    interval = CHECK_EVERY_SECONDS

    def enabled(self):
        return c.IS_WINDOWS

    def collect(self):
        raw = run_events_script()
        if raw is None:
            return None
        result = parse_events(raw)
        result["repairs"] = repairs.detect()
        return result

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at).astimezone().isoformat() if self.checked_at else None
        return {"supported": c.IS_WINDOWS, "checkedAt": checked, **(self.latest or {})}
