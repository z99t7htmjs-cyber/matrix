"""
Where Matrix keeps things, and its saved settings.

Program files (what the installer copies) and your data are kept apart, so
updating Matrix replaces the program without touching your data:

  Program:  %LOCALAPPDATA%\\Programs\\Matrix   (wherever this folder is)
  Data:     %LOCALAPPDATA%\\Matrix            (~/.matrix on other systems)
              known_devices.json   your device names, trusted and ignored devices
              settings.json        preferences such as opening the window at login
              oui.csv              manufacturer list (downloaded once)
              matrix.log           messages from the background server
"""

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.12.0"

APP_DIR = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"


def _data_dir():
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Matrix"
    else:
        base = Path.home() / ".matrix"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR = _data_dir()
KNOWN_DEVICES_FILE = DATA_DIR / "known_devices.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
OUI_FILE = DATA_DIR / "oui.csv"
LOG_FILE = DATA_DIR / "matrix.log"

EMPTY_KNOWN_DEVICES = {
    "_help": "Matrix keeps this file up to date when you name, trust or ignore devices in the dashboard. "
             "Keys are MAC addresses.",
    "devices": {},
}

DEFAULT_MODES = [
    {"id": "game", "name": "Game", "powerPlan": "High performance", "gameMode": True, "closeApps": [], "openApps": []},
    {"id": "homework", "name": "Homework", "powerPlan": "Balanced", "gameMode": False,
     "closeApps": ["Steam.exe", "Discord.exe"], "openApps": []},
    {"id": "battery", "name": "Battery", "powerPlan": "Power saver", "gameMode": False, "closeApps": [], "openApps": []},
]

# Added in 0.12 for auto-switch-by-power-source (see ensure_power_modes()). Kept as plain
# Modes -- same preview/apply machinery, same editable-in-Settings behavior -- rather than a
# parallel system. Locked-down closes the RGB/lighting stack (SignalRGB enumerates as three
# separate processes; closing only the main exe risks the Launcher or Service relaunching it)
# since on battery Rob is away from the Govee lights and the Arena 7 speakers entirely.
POWER_SWITCH_MODES = [
    {"id": "desktop", "name": "Desktop", "powerPlan": "High performance", "gameMode": None,
     "closeApps": [], "openApps": []},
    {"id": "locked-down", "name": "Locked-down", "powerPlan": "Power saver", "gameMode": None,
     "closeApps": ["SignalRgb.exe", "SignalRgbLauncher.exe", "SignalRgbService.exe"], "openApps": []},
]

DEFAULT_SETTINGS = {
    "openWindowAtLogin": False,  # at login, start in the background (False) or also open the window (True)
    "baselineAt": None,  # when "Trust all current devices" was last used
    "modes": DEFAULT_MODES,  # one-click modes; only what you set up in Settings
    "modeState": {"active": None, "previous": None, "appliedAt": None},  # for "Back to normal"
    "personaEnabled": True,  # ARGUS / MOMUS voice on Advisor cards, the digest and chat
    "autoVoiceEnabled": False,  # read critical alerts aloud automatically (read-aloud buttons always work)
    "livingLook": True,  # Living (animated) Overview vs. Classic (still, card grid only)
    "homeGatewayMac": None,  # this router's MAC, captured by "Trust all current devices" -- how Matrix recognizes home
    "awayFromHome": False,  # manual override: pause device scanning right now, whatever network this is
    "autoSwitchPower": False,  # off by default -- the one setting that lets Matrix change something with no click
    "showPowerModeDot": True,  # small Desktop/Locked-down indicator near the top of the app
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path, data):
    """Write to a temporary file, then swap it in, so a crash can't leave half a file.

    Windows refuses the swap while anything else has the file open for a moment
    (Matrix's own background scan, or antivirus checking the file), so retry
    briefly instead of failing.
    """
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    temp.unlink(missing_ok=True)
    raise ValueError("Windows kept the file busy, so the change wasn't saved. Please try again.")


# --- settings -------------------------------------------------------------------------

def load_settings():
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_SETTINGS, **(saved if isinstance(saved, dict) else {})}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)


def save_settings(**changes):
    settings = {**load_settings(), **changes}
    write_json_atomic(SETTINGS_FILE, settings)
    return settings


def ensure_power_modes():
    """0.12: add the Desktop / Locked-down modes if they're missing.

    DEFAULT_SETTINGS only seeds a brand-new settings.json -- anyone who already has one
    (everyone upgrading) keeps their saved "modes" list as-is, so the two new modes would
    silently never appear without this. Call once at startup, after the version that
    introduced them. Existing modes (and any renaming Rob's done) are left untouched;
    this only appends what's missing, matching by id.
    """
    settings = load_settings()
    modes = list(settings.get("modes") or [])
    existing_ids = {m.get("id") for m in modes}
    missing = [m for m in POWER_SWITCH_MODES if m["id"] not in existing_ids]
    if missing:
        save_settings(modes=modes + missing)


# --- moving device names from older versions -----------------------------------------

def _device_count(path):
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("devices", {}))
    except (OSError, json.JSONDecodeError, AttributeError):
        return 0


def migrate_known_devices():
    """First run of this version: bring over names saved by an older Matrix folder.

    Older versions kept known_devices.json inside the program's server folder,
    usually somewhere under Downloads. Pick the copy with the most devices
    (newest wins a tie) so nobody has to rename everything again.
    """
    if KNOWN_DEVICES_FILE.exists():
        return None
    downloads = Path.home() / "Downloads"
    candidates = [APP_DIR / "server" / "known_devices.json"]
    for pattern in ("matrix/server/known_devices.json", "*/matrix/server/known_devices.json",
                    "*/*/matrix/server/known_devices.json"):
        candidates.extend(downloads.glob(pattern))
    found = [p for p in candidates if p.is_file() and _device_count(p) > 0]
    if found:
        best = max(found, key=lambda p: (_device_count(p), p.stat().st_mtime))
        shutil.copyfile(best, KNOWN_DEVICES_FILE)
        return best
    write_json_atomic(KNOWN_DEVICES_FILE, EMPTY_KNOWN_DEVICES)
    return None
