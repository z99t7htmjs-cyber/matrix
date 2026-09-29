"""
Tune-up: what's worth cleaning up or adjusting on this PC.

Read-only, like everything else. Matrix points you to the right Windows
page instead of changing settings itself, and it sticks to settings
Microsoft supports; no registry "speed hacks".

  * Startup apps, and whether each is enabled (what Task Manager shows)
  * Installed programs and Store apps, with commonly preinstalled extras
    flagged and ranked by real cost (disk space, starting with Windows,
    a second antivirus) -- not just "found", so the noise stays low
  * Game Mode, hardware-accelerated GPU scheduling, Storage Sense, power plan
  * Battery vs. plugged-in power settings side by side, and battery health
    (design vs. current capacity, cycle count) on laptops
  * How much space temporary files use
  * Running services, and the full app/startup lists, so day-to-day changes
    can be compared (see changes.py)
"""

import base64
import json
import re

import collectors as c
from periodic import PeriodicMonitor

# Everything in this batch (startup apps, installed programs, temp files, battery health,
# power settings) changes over days, not minutes -- doubled from 30 to 60 min to roughly
# halve the background cost of the recursive TEMP-folder scan and the powercfg battery
# report XML round-trip. "Check again" in the UI still forces an immediate run regardless
# (see periodic.py's run_now_and_wait()), so this only affects the passive background cadence.
CHECK_EVERY_SECONDS = 3600

TUNEUP_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$r = [ordered]@{}

# Startup apps with their enabled/disabled state (Task Manager keeps it under StartupApproved)
$approved = @{}
foreach ($p in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run',
               'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run',
               'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32',
               'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder',
               'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder') {
  $key = Get-Item $p
  if ($key) { foreach ($n in $key.GetValueNames()) { $b = $key.GetValue($n); if ($b) { $approved[$n] = (($b[0] % 2) -eq 0) } } }
}
$r.startup = @(Get-CimInstance Win32_StartupCommand | ForEach-Object {
  $id = if ($_.Location -like '*Startup*') { Split-Path $_.Command -Leaf } else { $_.Name }
  $enabled = if ($approved.ContainsKey($_.Name)) { $approved[$_.Name] } elseif ($approved.ContainsKey($id)) { $approved[$id] } else { $true }
  [ordered]@{ name = "$($_.Name)"; command = "$($_.Command)"; location = "$($_.Location)"; enabled = $enabled }
})

# Installed desktop programs
$keys = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
$r.apps = @(Get-ItemProperty $keys | Where-Object { $_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName } |
  ForEach-Object { [ordered]@{ name = "$($_.DisplayName)"; publisher = "$($_.Publisher)";
                               sizeMb = [math]::Round(([double]$_.EstimatedSize) / 1024); installed = "$($_.InstallDate)" } })

# Store apps installed for this user (not frameworks or core system packages)
$r.storeApps = @(Get-AppxPackage | Where-Object { -not $_.IsFramework -and "$($_.SignatureKind)" -eq 'Store' } |
  ForEach-Object { [ordered]@{ name = "$($_.Name)"; publisher = "$($_.PublisherDisplayName)" } })

# Services currently running (for "what changed?")
$r.services = @(Get-Service | Where-Object { $_.Status -eq 'Running' } | Select-Object -ExpandProperty Name | Sort-Object)

# Settings worth knowing about
$gb = Get-ItemProperty 'HKCU:\Software\Microsoft\GameBar'
$r.gameMode = if ($gb -and $null -ne $gb.AutoGameModeEnabled) { [bool]$gb.AutoGameModeEnabled } else { $true }
$gd = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
$r.gpuScheduling = if ($gd -and $null -ne $gd.HwSchMode) { $gd.HwSchMode -eq 2 } else { $null }
$ss = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy'
$r.storageSense = if ($ss) { $ss.'01' -eq 1 } else { $false }
$r.powerPlan = "$(powercfg /getactivescheme)"
$r.tempMb = [math]::Round(((Get-ChildItem $env:TEMP -Recurse -Force -File | Measure-Object Length -Sum).Sum) / 1MB)

# Battery vs. plugged-in settings, side by side (only meaningful on a laptop)
function Get-PowerSetting($sub, $setting) {
  $out = powercfg /query SCHEME_CURRENT $sub $setting
  $ac = $out | Select-String 'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)'
  $dc = $out | Select-String 'Current DC Power Setting Index:\s*0x([0-9a-fA-F]+)'
  [ordered]@{
    ac = if ($ac) { [Convert]::ToInt32($ac.Matches[0].Groups[1].Value, 16) } else { $null }
    dc = if ($dc) { [Convert]::ToInt32($dc.Matches[0].Groups[1].Value, 16) } else { $null }
  }
}
$hasBattery = [bool](Get-CimInstance Win32_Battery)
$r.power = [ordered]@{
  hasBattery = $hasBattery
  screenTimeoutSec = Get-PowerSetting 'SUB_VIDEO' 'VIDEOIDLE'
  sleepTimeoutSec = Get-PowerSetting 'SUB_SLEEP' 'STANDBYIDLE'
  processorMaxPercent = Get-PowerSetting 'SUB_PROCESSOR' 'PROCTHROTTLEMAX'
}

# Battery health: design capacity vs. capacity now, and cycle count if Windows reports one
if ($hasBattery) {
  try {
    $reportPath = Join-Path $env:TEMP 'matrix-battery-report.xml'
    powercfg /batteryreport /xml /output $reportPath | Out-Null
    if (Test-Path $reportPath) {
      [xml]$bx = Get-Content $reportPath -Raw
      $batt = $bx.BatteryReport.Report.Batteries.Battery | Select-Object -First 1
      if ($batt -and $batt.DesignCapacity -and $batt.FullChargeCapacity) {
        $r.batteryHealth = [ordered]@{
          designMwh = [int]$batt.DesignCapacity
          fullChargeMwh = [int]$batt.FullChargeCapacity
          cycleCount = if ($batt.CycleCount) { [int]$batt.CycleCount } else { $null }
        }
      }
      Remove-Item $reportPath -ErrorAction SilentlyContinue
    }
  } catch {}
}

$r | ConvertTo-Json -Depth 4 -Compress
"""

# Commonly preinstalled programs and apps. Matched against name or publisher
# (lowercase substring). The note says why it's flagged; flagged is not "bad",
# just "check whether you use it". Real cost (below) decides whether it's
# actually shown, so tiny built-in extras don't nag.
PREINSTALLED = [
    (("mcafee",), "Antivirus trial. Windows Security already protects you; two antivirus programs slow the PC and can conflict.", True),
    (("norton",), "Antivirus trial. Windows Security already protects you; two antivirus programs slow the PC and can conflict.", True),
    (("wildtangent",), "Preinstalled game store and trials.", False),
    (("expressvpn",), "Preinstalled VPN trial.", False),
    (("booking.com", "priceline"), "Preinstalled travel shortcut.", False),
    (("asus giftbox", "asusgiftbox"), "ASUS promotional app store.", False),
    (("wps office",), "Preinstalled office trial.", False),
    (("candycrush", "king.com"), "Preinstalled game.", False),
    (("tiktok", "bytedance"), "Preinstalled social app.", False),
    (("facebook", "instagram"), "Preinstalled social app.", False),
    (("disney",), "Preinstalled streaming app.", False),
    (("amazon.com.amazon", "amazonvideo", "prime video"), "Preinstalled shopping or streaming app.", False),
    (("spotifyab",), "Preinstalled music app (keep it if you use Spotify).", False),
    (("dropbox promotion", "dropboxoem"), "Dropbox promotional offer.", False),
]

# Things that look like bloat but are important on this kind of laptop.
KEEP = [
    (("armoury crate", "armourycrate"), "Keep: controls fans, performance modes and lighting on ASUS ROG laptops."),
    (("myasus",), "Keep: ASUS drivers, BIOS updates and battery care settings."),
    (("nvidia", "geforce"), "Keep: graphics driver and settings."),
    (("amd software", "radeon software"), "Keep: graphics driver and settings."),
]

# Real-cost thresholds, so "flagged" means "worth your time", not just "found".
BIG_MB = 500
NOTABLE_MB = 50


def _match(rules, *texts):
    haystack = " ".join(t.lower() for t in texts if t)
    return next((note for words, note, *_ in rules if any(w in haystack for w in words)), None)


def _is_antivirus(rules, *texts):
    haystack = " ".join(t.lower() for t in texts if t)
    return any(antivirus for words, _note, antivirus in rules if any(w in haystack for w in words))


def _impact(app, startup_names, antivirus):
    """Score + plain-language reasons an app actually costs something. Zero means no real cost found."""
    score, reasons = 0, []
    size = app.get("sizeMb")
    if size and size >= BIG_MB:
        score += 3
        reasons.append(f"{size / 1000:.1f} GB of disk space" if size >= 1000 else f"{size} MB of disk space")
    elif size and size >= NOTABLE_MB:
        score += 1
        reasons.append(f"{size} MB of disk space")
    if app["name"] in startup_names:
        score += 2
        reasons.append("starts with Windows")
    if antivirus:
        score += 4
        reasons.append("a second antivirus program")
    return score, reasons


def _mb(mwh):
    return round(mwh) if mwh is not None else None


def parse_power_settings(raw):
    power = raw.get("power") or {}
    if not power.get("hasBattery"):
        return None

    def pair(key, unit_seconds=True):
        v = power.get(key) or {}
        ac, dc = v.get("ac"), v.get("dc")
        if not unit_seconds:
            return {"ac": ac, "dc": dc}
        to_min = lambda s: None if s is None else round(s / 60) if s else 0  # 0 = "never"
        return {"ac": to_min(ac), "dc": to_min(dc)}

    screen = pair("screenTimeoutSec")
    sleep = pair("sleepTimeoutSec")
    processor = pair("processorMaxPercent", unit_seconds=False)
    maxed_on_battery = processor.get("dc") == 100
    return {
        "screenTimeoutMin": screen, "sleepTimeoutMin": sleep, "processorMaxPercent": processor,
        "maxedOutOnBattery": maxed_on_battery,
    }


def parse_battery_health(raw):
    health = raw.get("batteryHealth")
    if not health or not health.get("designMwh"):
        return None
    design, full = health["designMwh"], health.get("fullChargeMwh")
    if not full:
        return None
    return {
        "designMwh": design, "fullChargeMwh": full,
        "healthPercent": round(full / design * 100) if design else None,
        "cycleCount": health.get("cycleCount"),
    }


def parse_tuneup(raw):
    startup_names = {s["name"] for s in raw.get("startup") or []}
    apps = []
    for a in raw.get("apps") or []:
        flag = _match(PREINSTALLED, a["name"], a.get("publisher"))
        antivirus = _is_antivirus(PREINSTALLED, a["name"], a.get("publisher")) if flag else False
        score, reasons = _impact(a, startup_names, antivirus) if flag else (0, [])
        apps.append({**a, "kind": "program", "flag": flag, "keep": _match(KEEP, a["name"], a.get("publisher")),
                     "impact": score, "reasons": reasons})
    for a in raw.get("storeApps") or []:
        friendly = a["name"].split(".")[-1]  # "king.com.CandyCrushSaga" -> "CandyCrushSaga"
        flag = _match(PREINSTALLED, a["name"], a.get("publisher"))
        antivirus = _is_antivirus(PREINSTALLED, a["name"], a.get("publisher")) if flag else False
        score, reasons = _impact({"name": friendly, "sizeMb": None}, startup_names, antivirus) if flag else (0, [])
        apps.append({"name": friendly, "packageName": a["name"], "publisher": a.get("publisher"), "sizeMb": None,
                     "kind": "store", "flag": flag, "keep": _match(KEEP, a["name"]), "impact": score, "reasons": reasons})

    plan = re.search(r"\(([^)]+)\)\s*$", raw.get("powerPlan") or "")
    startup = [{**s, "keep": _match(KEEP, s["name"], s.get("command"))} for s in raw.get("startup") or []]
    # Only show extras with a real, explainable cost; a second antivirus always counts.
    flagged = sorted((a for a in apps if a["flag"] and not a["keep"] and a["impact"] > 0),
                     key=lambda a: a["impact"], reverse=True)
    services = raw.get("services") or []
    return {
        "startup": sorted(startup, key=lambda s: (not s["enabled"], s["name"].lower())),
        "flagged": flagged,
        "largest": sorted((a for a in apps if a.get("sizeMb")), key=lambda a: a["sizeMb"], reverse=True)[:10],
        "appCount": len(apps),
        "gameMode": raw.get("gameMode"),
        "gpuScheduling": raw.get("gpuScheduling"),
        "storageSense": raw.get("storageSense"),
        "powerPlan": plan.group(1) if plan else None,
        "tempMb": raw.get("tempMb"),
        "power": parse_power_settings(raw),
        "batteryHealth": parse_battery_health(raw),
        # Full names, for "what changed?" (server/changes.py); not shown directly in Tune-up.
        "startupNames": sorted(startup_names),
        "installedNames": sorted({a["name"] for a in apps}),
        "services": sorted(services) if isinstance(services, list) else ([services] if services else []),
    }


def run_tuneup_script():
    encoded = base64.b64encode(TUNEUP_SCRIPT.encode("utf-16-le")).decode("ascii")
    output = c.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=120)
    start = output.find("{")
    if start < 0:
        return None
    try:
        raw = json.loads(output[start:])
    except json.JSONDecodeError:
        return None
    for key in ("startup", "apps", "storeApps"):
        if isinstance(raw.get(key), dict):
            raw[key] = [raw[key]]
    if isinstance(raw.get("services"), str):
        raw["services"] = [raw["services"]]
    return raw


class TuneupMonitor(PeriodicMonitor):
    name = "Tune-up"
    interval = CHECK_EVERY_SECONDS

    def enabled(self):
        return c.IS_WINDOWS

    def collect(self):
        raw = run_tuneup_script()
        return parse_tuneup(raw) if raw is not None else None

    def snapshot(self):
        return {"supported": c.IS_WINDOWS, "checked": self.checked_at is not None, **(self.latest or {})}
