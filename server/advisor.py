"""
The Advisor: turns live data into specific, explainable suggestions.

Each rule is a small function that looks at the current state and returns
zero or more suggestions made with suggestion(...):

  id          stable key, e.g. "defender-realtime"
  area        security | performance | maintenance | network | stability | tune-up | setup
  urgency     critical   flashes, notifies, needs doing now
              attention  worth doing soon; calm
              fyi        good to know; archives itself if left alone for a week
  kind        condition  Matrix re-checks it and it resolves itself once fixed
              choice     a condition you may decide to keep as it is ("Keep as is")
              event      something that happened; you acknowledge it ("Got it")
  check       which background check verifies it ("health", "events", "tuneup",
              "network", "system"), used by the "Check again" button
  fingerprint what makes this item "the same" (defaults to the title). A kept or
              acknowledged item only comes back if its fingerprint changes.
  transient   short-lived readings (CPU busy right now): shown live, never archived
  steps       what to do; text in `backticks` is shown as a command
  plan        a troubleshooting plan id (see plans.py) that supplies the steps

Rules only use facts Matrix measured, so every suggestion traces back to a reading.
Lifecycle (active / snoozed / kept / resolved) is handled by alerts.py.
"""

from datetime import date, datetime

URGENCY_ORDER = {"critical": 0, "attention": 1, "fyi": 2}

WINDOWS_SECURITY = "Open Windows Security (search for it in the Start menu)"


def suggestion(id, area, urgency, title, detail, steps, *, kind="condition", check=None,
               fingerprint=None, transient=False, plan=None):
    return {
        "id": id, "area": area, "urgency": urgency, "title": title, "detail": detail, "steps": steps,
        "kind": kind, "check": check, "fingerprint": fingerprint or title, "transient": transient, "plan": plan,
    }


def _days_ago(iso):
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 999
    return (datetime.now(when.tzinfo) - when).total_seconds() / 86400


def _when(iso):
    days = _days_ago(iso)
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    return f"{int(days)} days ago"


# --- security ---------------------------------------------------------------------------

def defender_rules(state):
    health = state["health"]
    if not health.get("checkedAt"):
        return []
    d = health.get("defender")
    if not d:
        return [suggestion("defender-missing", "security", "attention", "Microsoft Defender isn't reporting",
                           "Windows didn't return Defender status. Another antivirus may be managing protection.",
                           [f"{WINDOWS_SECURITY} → Virus & threat protection, and check which program is protecting this PC."],
                           check="health", kind="choice")]
    out = []
    if not d.get("realtime"):
        out.append(suggestion("defender-realtime", "security", "critical", "Real-time antivirus protection is off",
                              "Files aren't being scanned as they're opened or downloaded.",
                              [f"{WINDOWS_SECURITY} → Virus & threat protection.",
                               "Under Virus & threat protection settings, choose Manage settings.",
                               "Turn Real-time protection On."], check="health"))
    age = d.get("signatureAgeDays") or 0
    if age >= 3:
        out.append(suggestion("defender-signatures", "security", "attention",
                              f"Antivirus definitions are {age} days old",
                              "Defender normally updates at least daily. Old definitions miss new threats.",
                              [f"{WINDOWS_SECURITY} → Virus & threat protection → Protection updates.",
                               "Click Check for updates."], check="health", fingerprint="defender-signatures"))
    scan_age = d.get("quickScanAgeDays")
    if scan_age is not None and scan_age > 14:
        never = scan_age > 3650
        out.append(suggestion("defender-scan", "security", "fyi",
                              "No antivirus scan on record" if never else f"Last quick scan was {scan_age} days ago",
                              "Real-time protection catches most threats, but a periodic scan checks files already on disk.",
                              [f"{WINDOWS_SECURITY} → Virus & threat protection → Quick scan."],
                              check="health", fingerprint="defender-scan"))

    for threat in health.get("threats") or []:
        if _days_ago(threat["time"]) > 7:
            continue
        files = ", ".join(threat.get("files") or [])[:160]
        if threat.get("removed"):
            out.append(suggestion(f"threat-{threat['id']}", "security", "attention",
                                  f"Defender removed a threat {_when(threat['time'])}: {threat['name']}",
                                  f"It was blocked or cleaned automatically. {('Found in: ' + files) if files else ''}",
                                  ["Nothing to do if you recognize where it came from (a download you didn't trust, say).",
                                   "If it keeps coming back, run a full scan and check your browser extensions."],
                                  kind="event", check="health", fingerprint=threat["id"]))
        else:
            out.append(suggestion(f"threat-{threat['id']}", "security", "critical",
                                  f"Defender found a threat it couldn't remove: {threat['name']}",
                                  f"Detected {_when(threat['time'])}. {('Found in: ' + files) if files else ''}",
                                  [f"{WINDOWS_SECURITY} → Virus & threat protection → Protection history.",
                                   "Choose the threat and follow the recommended action (usually Remove or Quarantine).",
                                   "Then run a Full scan."], check="health", fingerprint=threat["id"]))
    return out


def firewall_rules(state):
    profiles = state["health"].get("firewall") or []
    off = [p["name"] for p in profiles if not p.get("enabled")]
    if not off:
        return []
    return [suggestion("firewall-off", "security", "critical", f"Firewall is off for: {', '.join(off)}",
                       "The firewall blocks unwanted incoming connections. Turning it off exposes every listening service.",
                       [f"{WINDOWS_SECURITY} → Firewall & network protection.",
                        "Select each network type marked Off and switch Microsoft Defender Firewall On."], check="health")]


def account_rules(state):
    health = state["health"]
    out = []
    if health.get("uacEnabled") is False:
        out.append(suggestion("uac-off", "security", "attention", "User Account Control is disabled",
                              "Programs can make system-wide changes without asking you first.",
                              ["Search the Start menu for \"Change User Account Control settings\".",
                               "Move the slider back to the default (second from top) and click OK.",
                               "Restart when prompted."], check="health"))
    if health.get("rdpEnabled"):
        out.append(suggestion("rdp-on", "security", "attention", "Remote Desktop is turned on",
                              "Other devices can try to log in to this PC remotely. It's a common target for password guessing.",
                              ["Open Settings → System → Remote Desktop.",
                               "Turn Remote Desktop Off unless you actually use it."], check="health", kind="choice"))
    return out


# --- maintenance ------------------------------------------------------------------------

def update_rules(state):
    health = state["health"]
    out = []
    if health.get("rebootPending"):
        out.append(suggestion("reboot-pending", "maintenance", "attention", "Restart to finish installing updates",
                              "Windows has installed updates that only take effect after a restart.",
                              ["Save your work, then Start → Power → Restart (or \"Update and restart\")."], check="health"))
    last = health.get("lastUpdate")
    if last:
        try:
            days = (date.today() - date.fromisoformat(last)).days
        except ValueError:
            days = 0
        if days > 40:
            out.append(suggestion("updates-old", "maintenance", "attention",
                                  f"Last Windows update was {days} days ago",
                                  "Microsoft releases security fixes every month, so this PC has probably missed at least one.",
                                  ["Open Settings → Windows Update.", "Click Check for updates and install everything offered.",
                                   "Restart when asked."], check="health", fingerprint="updates-old"))
    # Get-HotFix (above) only ever shows updates that installed successfully, so it can't
    # tell "hasn't had a new update to offer" apart from "has been failing every attempt."
    # This looks at the actual result of the most recent attempt instead.
    attempt = health.get("lastUpdateAttempt")
    if attempt and not attempt.get("succeeded"):
        days_since = _days_ago(attempt.get("time"))
        if days_since >= 2:  # give Windows' own automatic retry a couple of days first
            whole_days = int(days_since)
            out.append(suggestion("update-failed", "maintenance", "attention",
                                  "Windows Update's last attempt failed",
                                  f"The most recent update Windows tried to install"
                                  f"{' (' + attempt['title'] + ')' if attempt.get('title') else ''} didn't succeed, "
                                  f"about {whole_days} day{'s' if whole_days != 1 else ''} ago, and nothing has "
                                  "installed successfully since.",
                                  ["Open Settings → Windows Update and click \"Check for updates\" to retry.",
                                   "If it keeps failing, Settings → System → Troubleshoot → Other troubleshooters → "
                                   "Windows Update has a built-in fixer."],
                                  check="health", fingerprint=f"update-failed-{attempt.get('time')}"))
    return out


def startup_rules(state):
    tuneup = state.get("tuneup") or {}
    if tuneup.get("startup") is not None:
        enabled = [a["name"] for a in tuneup["startup"] if a["enabled"] and not a.get("keep")]
    else:
        enabled = state["health"].get("startupApps") or []
    if len(enabled) <= 8:
        return []
    preview = ", ".join(enabled[:5]) + ("…" if len(enabled) > 5 else "")
    return [suggestion("startup-apps", "maintenance", "fyi", f"{len(enabled)} apps start with Windows",
                       f"Each one slows boot and uses memory in the background ({preview}).",
                       ["Open the Tune-up view to see the full list.",
                        "Disable the ones you don't need running all the time in Settings → Apps → Startup. "
                        "They still work when you open them yourself."],
                       check="tuneup", kind="choice", fingerprint=",".join(sorted(enabled)))]


def uptime_rules(state):
    uptime = state["system"].get("uptimeSeconds")
    if not uptime or uptime < 7 * 86400:
        return []
    days = uptime // 86400
    return [suggestion("uptime", "maintenance", "fyi", f"No restart in {days} days",
                       "A restart clears leaked memory and finishes pending updates. Note: \"Shut down\" doesn't count, "
                       "because Windows Fast Startup resumes from hibernation instead of starting fresh.",
                       ["Start → Power → Restart."], check="system", kind="choice", fingerprint="uptime")]


def disk_rules(state):
    out = []
    for disk in state["system"].get("disks") or []:
        free, total, used = disk["freeGb"], disk["totalGb"], disk["usedPercent"]
        if total < 1:
            continue
        if free < 2 or used >= 98:
            urgency = "critical"
        elif free < 10 or used >= 95:
            urgency = "attention"
        elif free < 25 or used >= 90:
            urgency = "fyi"
        else:
            continue
        out.append(suggestion(f"disk-{disk['mount']}", "maintenance", urgency,
                              f"Drive {disk['mount']} is {'nearly out of space' if urgency == 'critical' else 'almost full'} ({free:g} GB free)",
                              "Windows needs free space for updates, virtual memory and temporary files. A full drive causes slowdowns and failed updates.",
                              ["Open Settings → System → Storage → Temporary files, and remove what you don't need.",
                               "Turn on Storage Sense on the same page to clean up automatically.",
                               "Check Settings → Apps → Installed apps, sorted by size, for games or apps you no longer use."],
                              check="system", fingerprint=f"disk-{disk['mount']}-{urgency}"))
    return out


def drive_rules(state):
    """Is a drive actually dying, not just full -- disk_rules() above only ever looks at
    free space, so a nearly-empty drive that's failing wouldn't raise anything there."""
    out = []
    drives = state.get("drives") or {}
    if not drives.get("checkedAt"):
        return out
    for disk in drives.get("disks") or []:
        name = disk.get("model") or f"Drive {disk.get('id', '?')}"
        status = disk.get("healthStatus")
        if status and status not in ("Healthy", "Unknown"):
            urgency = "critical" if status == "Unhealthy" else "attention"
            out.append(suggestion(f"drive-health-{disk['id']}", "maintenance", urgency,
                                  f"Windows reports \"{name}\" as {status.lower()}",
                                  "This is Windows' own overall assessment of the drive (Get-PhysicalDisk), not "
                                  "just how full it is. A drive can report this even with plenty of free space.",
                                  ["Back up anything on this drive you can't afford to lose, now, before doing anything else.",
                                   "Open Settings → System → Storage → Advanced storage settings → Disks & volumes "
                                   "to see which drive this is and its partitions.",
                                   "If it stays Warning/Unhealthy, plan to replace the drive."],
                                  check="drives", fingerprint=f"drive-health-{disk['id']}-{status}"))
        wear = disk.get("wearPercent")
        if wear is not None and wear >= 80:
            urgency = "critical" if wear >= 95 else "attention"
            out.append(suggestion(f"drive-wear-{disk['id']}", "maintenance", urgency,
                                  f"\"{name}\" is {wear}% through its rated write endurance",
                                  "SSDs wear out from total data written over their life, not age or free space. "
                                  f"{wear}% isn't a sudden failure risk by itself, but it's worth planning around "
                                  "before it gets much higher.",
                                  ["Back up what matters on this drive.",
                                   "No need to replace it today -- just don't be caught off guard later."],
                                  check="drives", fingerprint=f"drive-wear-{disk['id']}-{wear // 5}"))
    return out


def thermal_rules(state):
    """A rising resting (idle) GPU temperature over weeks -- an early, honest proxy for dust
    buildup or degraded cooling, since Matrix has no way to read actual fan RPM."""
    out = []
    trend = state.get("thermalTrend") or {}
    risen = trend.get("risenC")
    if risen is None:
        return out
    if risen >= 8:
        urgency = "critical" if risen >= 12 else "attention"
        out.append(suggestion("idle-temp-rising", "maintenance", urgency,
                              f"Resting GPU temperature has crept up about {risen:g}°C",
                              f"Comparing the coolest reading each day while the PC was basically idle: it's "
                              f"averaging around {trend['baselineC']:g}°C earlier in the {trend['sampleDays']}-day "
                              f"record Matrix has kept vs. {trend['recentC']:g}°C more recently. This is a proxy, "
                              "not a certainty -- room temperature, where the laptop sits, or a driver update "
                              "could also explain part of it, not just dust.",
                              ["Power off and, if you're comfortable opening it, check the intake vents and fan "
                               "for visible dust or pet hair.",
                               "If you'd rather not open it yourself, a compressed-air blast through the vents "
                               "while it's off can clear a lot without opening the case.",
                               "If resting temps don't come back down, it may be worth a professional cleaning."],
                              check=None, kind="condition",
                              fingerprint=f"idle-temp-rising-{int(risen // 2)}"))
    return out


# --- performance ------------------------------------------------------------------------

def load_rules(state):
    system = state["system"]
    if not system.get("available") or "cpu" not in system:
        return []
    out = []
    processes = system.get("processes") or []
    top_cpu = max(processes, key=lambda p: p["cpu"], default=None)
    top_mem = max(processes, key=lambda p: p["memMb"], default=None)

    history = system["cpu"].get("history") or []
    recent = history[-15:]  # about 30 seconds
    if len(recent) >= 10 and sum(recent) / len(recent) >= 85:
        who = f" {top_cpu['name']} is using the most ({top_cpu['cpu']:g}%)." if top_cpu else ""
        out.append(suggestion("cpu-high", "performance", "fyi", "CPU has been busy for the last 30 seconds",
                              f"Average load is {sum(recent) / len(recent):.0f}%.{who}",
                              ["If you're not gaming or rendering, open Task Manager (Ctrl+Shift+Esc) → Processes, sorted by CPU.",
                               "End or update the program at the top if it shouldn't be that busy."],
                              check="system", transient=True))

    memory = system.get("memory") or {}
    if memory.get("usage", 0) >= 88:
        who = f" {top_mem['name']} is using {top_mem['memMb'] / 1000:.1f} GB." if top_mem else ""
        out.append(suggestion("memory-high", "performance", "fyi", f"Memory is {memory['usage']:.0f}% full",
                              f"When memory runs out Windows swaps to disk, which makes everything slow.{who}",
                              ["Close programs or browser tabs you aren't using.",
                               "If this happens often, check Task Manager → Startup apps for things running in the background."],
                              check="system", transient=True))

    temps = [t for t in (system.get("gpuTempHistory") or []) if t is not None]
    gpu = (system.get("gpus") or [None])[0]
    cool_steps = ["Make sure the vents aren't blocked, and use a hard, flat surface.",
                  "Clean dust from the fans and vents.",
                  "In Armoury Crate, try Performance or Silent mode instead of Turbo."]
    if len(temps) >= 50 and min(temps) >= 90:
        out.append(suggestion("gpu-overheating", "performance", "critical",
                              f"GPU has been overheating for 2 minutes ({temps[-1]:.0f}°C)",
                              "Sustained temperatures this high throttle performance and wear the hardware.",
                              ["Pause the game or heavy app to let it cool."] + cool_steps, check="system", transient=True))
    elif gpu and gpu.get("tempC") and gpu["tempC"] >= 85:
        out.append(suggestion("gpu-hot", "performance", "fyi", f"GPU is running hot ({gpu['tempC']:.0f}°C)",
                              "High temperatures cause throttling (lower FPS). Normal briefly during games; worth watching if it stays.",
                              cool_steps, check="system", transient=True))

    battery = system.get("battery")
    if battery and not battery["plugged"] and battery["percent"] <= 20:
        out.append(suggestion("battery-low", "performance", "attention", f"Battery at {battery['percent']}%",
                              "Plug in soon. Windows will start limiting performance to save power.",
                              ["Connect the charger."], check="system", transient=True))
    return out


# --- network ----------------------------------------------------------------------------

def network_rules(state):
    nodes = [n for n in state["network"].get("nodes") or [] if not n.get("ignored")]
    out = []
    internet = next((n for n in nodes if n["id"] == "internet"), None)
    if internet and internet["status"] != "online" and len(nodes) > 1:
        out.append(suggestion("internet-down", "network", "attention", "No internet connection detected",
                              "This PC has no active connections to any internet address.",
                              ["Check that Wi-Fi or Ethernet is connected (taskbar network icon).",
                               "Restart the router: unplug it for 30 seconds, then plug it back in."],
                              check="network", transient=True))

    unknown = [n for n in nodes if any(a["kind"] == "new-device" for a in n.get("alerts", []))]
    baseline = state["meta"].get("baselineAt")
    if unknown and baseline:
        listed = ", ".join(f"{n['name']} ({n.get('ip') or 'no IP'})" for n in unknown[:5])
        out.append(suggestion("new-devices", "network", "critical",
                              f"{len(unknown)} new device{'s' if len(unknown) > 1 else ''} joined your network",
                              f"Not here when you trusted your devices on {baseline[:10]}: {listed}.",
                              ["Open the Network view and click each one; try Identify to learn more about it.",
                               "If it's expected (a visitor, a new gadget), name it, trust it or ignore it.",
                               "If nobody recognizes it, change your Wi-Fi password."],
                              check="network", fingerprint=",".join(sorted(n["id"] for n in unknown))))
    elif unknown:
        listed = ", ".join(n.get("ip") or n["id"] for n in unknown[:5])
        out.append(suggestion("unknown-devices", "network", "attention",
                              f"{len(unknown)} device{'s' if len(unknown) > 1 else ''} on your network couldn't be identified",
                              f"Matrix found no name or maker for: {listed}.",
                              ["If these belong to people you live with, use \"Trust all current devices\" in the Network view. "
                               "Matrix will then only alert you about devices that show up later.",
                               "Or click each one to identify, name or ignore it."],
                              check="network", kind="choice", fingerprint=",".join(sorted(n["id"] for n in unknown))))

    unconfirmed = [n for n in nodes if any(a["kind"] == "unconfirmed-device" for a in n.get("alerts", []))]
    if unconfirmed:
        names = ", ".join(n["name"] for n in unconfirmed[:4]) + ("…" if len(unconfirmed) > 4 else "")
        out.append(suggestion("unconfirmed-devices", "network", "fyi",
                              f"{len(unconfirmed)} device{'s' if len(unconfirmed) > 1 else ''} identified automatically",
                              f"Matrix guessed from names and makers: {names}.",
                              ["Click each one on the map to confirm or correct the guess,",
                               "or trust them all at once with \"Trust all current devices\" in the Network view."],
                              check="network", kind="choice", fingerprint=",".join(sorted(n["id"] for n in unconfirmed))))
    return out


# --- stability --------------------------------------------------------------------------

def stability_rules(state):
    events = state.get("events") or {}
    plan = (state.get("plans") or {}).get("crashes") or {}
    out = []

    if plan.get("state") == "active":
        counted = plan["counted"]
        latest = counted[0]
        blue = [c for c in counted if c["kind"] == "bluescreen" and _days_ago(c["time"]) <= 2]
        urgency = "critical" if len(counted) >= 3 or len(blue) >= 2 else "attention"
        what = "Blue screen" if latest["kind"] == "bluescreen" else "Unexpected restart"
        since = f" since your last repair ({plan['fixLabel']})" if plan.get("fixAt") else " this week"
        title = f"{what} {_when(latest['time'])}" + (
            f" · {len(counted)} crashes{since}" if len(counted) > 1 else " (after the last repair)" if plan.get("fixAt") else "")
        nxt = plan.get("next")
        detail = f"{latest['title']}{' · ' + latest['code'] if latest.get('code') else ''}. {latest['advice']}"
        if nxt:
            detail += f" Next step: {nxt['title']}."
        out.append(suggestion("crashes", "stability", urgency, title, detail, nxt["how"] if nxt else [],
                              kind="event", check="events", fingerprint=latest["time"], plan="crashes"))
    elif plan.get("state") == "watching":
        if plan.get("restartNeeded"):
            out.append(suggestion("crashes-restart", "stability", "attention", "Restart to finish the repair",
                                  f"{plan['fixLabel']}. Repairs take effect after a restart.",
                                  ["Save your work, then Start → Power → Restart."], check="events"))
        else:
            out.append(suggestion("crashes-watch", "stability", "fyi",
                                  f"Watching after repair: no crashes for {plan['quietDays']:.0f} of 3 days",
                                  f"{plan['fixLabel']}. If nothing crashes for 3 days, this resolves itself.",
                                  [], check="events", fingerprint="crashes-watch"))

    hardware = [h for h in events.get("hardware") or [] if not h.get("corrected") and _days_ago(h["time"]) <= 30]
    if hardware:
        out.append(suggestion("hardware-errors", "stability", "critical" if any(h.get("fatal") for h in hardware) else "attention",
                              "Windows logged hardware errors",
                              f"{len(hardware)} uncorrected hardware error(s) in the last 30 days. {hardware[0]['detail'][:160]}",
                              ["Remove any CPU, GPU or memory overclock.", "Update the BIOS through MyASUS.",
                               "Keep an eye on temperatures in the Performance view."],
                              kind="event", check="events", fingerprint=hardware[0]["time"]))

    for app in (events.get("apps") or [])[:5]:
        total = app["crashes"] + app["hangs"]
        threshold = 5 if app.get("helper") else 3  # Windows helpers crash on behalf of other code; only repeats matter
        if total < threshold:
            continue
        cause = f" The failing part is {app['module']}: {app['moduleOwner']}." if app.get("moduleOwner") else (
            f" The failing part is {app['module']}." if app.get("module") else "")
        if app.get("helper"):
            detail = f"{app['helper']}{cause}"
            steps = ["Look at what the failing part belongs to (above) and update or remove that program or driver.",
                     "If it's a thumbnail or codec add-on, try opening the folder that triggers it with thumbnails off."]
        else:
            detail = f"Repeated crashes usually mean the app needs an update, or its settings or cache are damaged.{cause}"
            steps = [f"Update {app['name']}, or reinstall it if updating doesn't help.",
                     "If the failing part is a graphics driver, update the NVIDIA driver too."]
        out.append(suggestion(f"app-crash-{app['name'].lower()}", "stability", "attention",
                              f"{app['name']} crashed or froze {total} times in two weeks", detail, steps,
                              kind="event", check="events", fingerprint=str(total // 3)))
    return out


def driver_rules(state):
    """A monthly nudge to check for driver updates. Matrix can't reliably compare against
    what NVIDIA/ASUS currently publish (no scraping), so this shows what's installed and
    points at the two places that actually know what's newest."""
    gpu = (state["system"].get("gpus") or [None])[0]
    if not gpu or not gpu.get("driverVersion"):
        return []
    month = date.today().strftime("%Y-%m")
    return [suggestion("driver-check", "maintenance", "fyi",
                       f"NVIDIA driver {gpu['driverVersion']} installed",
                       "Worth a monthly check for a newer Game Ready or Studio driver. Matrix doesn't fetch this "
                       "automatically (that would mean contacting NVIDIA), so this is just a reminder with the version "
                       "you're on now.",
                       ["Open the NVIDIA app → Drivers and check for updates.",
                        "MyASUS → Customer Support → Live Update also checks chipset, audio and BIOS drivers."],
                       check="system", kind="choice", fingerprint=f"driver-check-{gpu['driverVersion']}-{month}")]


# --- tune-up ----------------------------------------------------------------------------

def tuneup_rules(state):
    t = state.get("tuneup") or {}
    if not t.get("checked"):
        return []
    out = []
    flagged = t.get("flagged") or []
    if flagged:
        top = flagged[0]
        names = ", ".join(a["name"] for a in flagged[:4]) + ("…" if len(flagged) > 4 else "")
        antivirus = [a for a in flagged if "antivirus" in a["flag"].lower()]
        why = f" Worth the most: {top['name']} ({', '.join(top['reasons'])})." if top.get("reasons") else ""
        out.append(suggestion("preinstalled-apps", "tune-up", "attention" if antivirus else "fyi",
                              f"{len(flagged)} preinstalled extra{'s' if len(flagged) > 1 else ''} worth a look",
                              f"Ranked by real cost, not just found on the PC: {names}.{why}",
                              ["Open the Tune-up view to see why each one is flagged and ranked.",
                               "Uninstall the ones you don't use in Settings → Apps → Installed apps."],
                              check="tuneup", kind="choice", fingerprint=",".join(sorted(a["name"] for a in flagged))))
    if t.get("storageSense") is False and (t.get("tempMb") or 0) > 2000:
        out.append(suggestion("temp-files", "tune-up", "fyi", f"{t['tempMb'] / 1000:.1f} GB of temporary files",
                              "Temporary files build up over time. Storage Sense can clean them automatically.",
                              ["Open Storage settings and turn on Storage Sense.",
                               "Or choose Temporary files there to clean up now."],
                              check="tuneup", kind="choice", fingerprint="temp-files"))
    if t.get("gameMode") is False:
        out.append(suggestion("game-mode", "tune-up", "fyi", "Game Mode is off",
                              "Game Mode tells Windows to prioritize the game you're playing and pause background updates.",
                              ["Open Game Mode settings and turn it on."], check="tuneup", kind="choice"))

    power = t.get("power")
    if power and power.get("maxedOutOnBattery"):
        plan_name = t.get("powerPlan") or "your current plan"
        out.append(suggestion("power-maxed-battery", "tune-up", "attention",
                              "The processor can run at full power even on battery",
                              # Named specifically so this is checkable against what you see in Windows: this is
                              # NOT the simple power-mode slider in Settings (that one doesn't show this value).
                              # It's the deeper "Maximum processor state" setting under Power Options -> Change
                              # plan settings -> Change advanced power settings -> Processor power management,
                              # which Windows can leave at 100% on battery even while the plan itself is
                              # "Balanced" -- the plan name and the processor cap are two separate settings.
                              f"Windows reports \"{plan_name}\" has Maximum processor state set to 100% on battery "
                              "(Power Options -> Change plan settings -> Change advanced power settings -> "
                              "Processor power management). That's a different, deeper setting than the plan name "
                              "itself, so it can say 100% even while the plan you see in Settings is \"Balanced\".",
                              ["Open Power settings and cap \"Maximum processor state\" on battery to around 80%.",
                               "Or use the Battery mode in Modes (Tune-up view) once you've set it up."],
                              check="tuneup", kind="choice", fingerprint="power-maxed-battery"))
    battery = state["system"].get("battery")
    if battery and not battery["plugged"]:
        # This used to carry the ISO week number in its fingerprint, which meant the
        # fingerprint changed every 7 days no matter what -- alerts.py treats a changed
        # fingerprint as "the situation changed," so it forced this back to active even
        # after "Keep as is" or a snooze, every single week, forever. Matrix has no
        # reliable way to read Armoury Crate's actual current GPU mode (no standard
        # Windows API exposes it), so this can't be made state-aware the way the battery
        # power-plan warning was -- but it CAN stop pretending a dismissal didn't happen.
        # A stable fingerprint means "Keep as is" now actually sticks, like every other
        # fyi/choice item in this file.
        out.append(suggestion("gpu-mode-reminder", "tune-up", "fyi", "Biggest battery saver on this laptop: GPU mode",
                              "In Armoury Crate, switching the GPU mode to Eco (instead of Standard) is the single "
                              "biggest way to stretch battery life on an RTX laptop like this one. Matrix can't see "
                              "which GPU mode is currently active, so this can't confirm whether you're on it already.",
                              ["Open Armoury Crate → Performance and choose Eco mode while unplugged.",
                               "Switch back to Standard when you plug in again, or use a Battery mode once set up."],
                              check="system", kind="choice", fingerprint="gpu-mode-reminder"))
    bh = t.get("batteryHealth")
    if bh and bh.get("healthPercent") is not None:
        pct = bh["healthPercent"]
        if pct < 80:
            cycles = f", {bh['cycleCount']} charge cycles" if bh.get("cycleCount") else ""
            out.append(suggestion("battery-health", "tune-up", "attention" if pct < 60 else "fyi",
                                  f"Battery health is at {pct}% of new",
                                  f"Windows' battery report shows {pct}% of the original capacity remaining{cycles}. "
                                  "This is normal wear over time, not something Matrix can fix.",
                                  ["Avoid keeping it at 100% or fully drained for long stretches when you can.",
                                   "If it's dropped a lot recently, MyASUS → Customer Support can check for a battery issue."],
                                  check="tuneup", kind="choice", fingerprint="battery-health"))
    return out


def setup_rules(state):
    out = []
    if not state["system"].get("available"):
        out.append(suggestion("install-psutil", "setup", "attention", "Turn on live PC vitals",
                              "CPU, memory, disk and process readings need the psutil library.",
                              ["Run \"Install or Update Matrix\" again; it installs psutil for you.",
                               "Or run `python -m pip install psutil` and restart Matrix."]))
    if state["meta"].get("vendorDb") == "unavailable":
        out.append(suggestion("vendor-db", "setup", "fyi", "Maker lookup is unavailable",
                              "Matrix couldn't download the list of network-hardware makers. It retries each time Matrix starts.",
                              ["Make sure this PC is online, then restart Matrix."]))
    return out


RULES = [
    setup_rules, stability_rules, network_rules, defender_rules, firewall_rules, account_rules,
    update_rules, disk_rules, drive_rules, thermal_rules, load_rules, startup_rules, uptime_rules, tuneup_rules, driver_rules,
]

# One button per suggestion: open the Windows page that fixes it, or jump to a view.
ACTIONS = {
    "defender-missing": {"label": "Open Windows Security", "open": "security"},
    "defender-realtime": {"label": "Open Windows Security", "open": "security"},
    "defender-signatures": {"label": "Open Windows Security", "open": "security"},
    "defender-scan": {"label": "Open Windows Security", "open": "security"},
    "firewall-off": {"label": "Open Windows Security", "open": "security"},
    "uac-off": {"label": "Open UAC settings", "open": "uac"},
    "rdp-on": {"label": "Open Remote Desktop settings", "open": "remotedesktop"},
    "updates-old": {"label": "Open Windows Update", "open": "windowsupdate"},
    "update-failed": {"label": "Open Windows Update", "open": "windowsupdate"},
    "reboot-pending": {"label": "Open Windows Update", "open": "windowsupdate"},
    "startup-apps": {"label": "Open Startup apps", "open": "startupapps"},
    "cpu-high": {"label": "Open Task Manager", "open": "taskmanager"},
    "memory-high": {"label": "Open Task Manager", "open": "taskmanager"},
    "crashes": {"label": "See crash history", "view": "events"},
    "crashes-watch": {"label": "See crash history", "view": "events"},
    "hardware-errors": {"label": "Open Reliability Monitor", "open": "reliability"},
    "preinstalled-apps": {"label": "See in Tune-up", "view": "tuneup"},
    "temp-files": {"label": "Open Storage settings", "open": "storage"},
    "game-mode": {"label": "Open Game Mode settings", "open": "gamemode"},
    "power-maxed-battery": {"label": "Open Power settings", "open": "power"},
    "battery-health": {"label": "See in Tune-up", "view": "tuneup"},
    "driver-check": {"label": "Open Graphics settings", "open": "graphics"},
    "unknown-devices": {"label": "Go to Network", "view": "network"},
    "new-devices": {"label": "Go to Network", "view": "network"},
    "unconfirmed-devices": {"label": "Go to Network", "view": "network"},
}


def advise(state):
    suggestions = []
    for rule in RULES:
        try:
            suggestions.extend(rule(state))
        except Exception as err:  # one broken rule shouldn't hide the others
            print(f"[matrix] Advisor rule {rule.__name__} failed: {err}")
    for item in suggestions:
        if item["id"] in ACTIONS:
            item["action"] = ACTIONS[item["id"]]
        elif item["id"].startswith("disk-"):
            item["action"] = {"label": "Open Storage settings", "open": "storage"}
        elif item["id"].startswith("threat-"):
            item["action"] = {"label": "Open Windows Security", "open": "security"}
        elif item["id"].startswith("app-crash-"):
            item["action"] = {"label": "See crash details", "view": "events"}
    return sorted(suggestions, key=lambda s: URGENCY_ORDER[s["urgency"]])
