"""
One-click modes: Game / Homework / Battery (rename or add your own).

This is the one place Matrix changes settings instead of only pointing at
them, and it only ever does what you configured in Settings → Modes:

  * Windows power plan (Balanced, Power saver, High performance, ...)
  * Game Mode (on / off)
  * Apps to close (by process name) and apps to open (by path, command or
    a name Windows can resolve, like "notepad")

Every apply() is preceded by a preview() showing exactly what will change,
and the power plan + Game Mode (not the app list -- Windows doesn't
remember what was open before) can be put back with revert().

Checking whether Armoury Crate's Silent / Performance / Turbo modes can be
switched from here is still open (ASUS has no public interface); this only
touches settings Windows itself exposes.
"""

import re
import subprocess

import collectors as c
import paths

SCHEME_LINE = re.compile(r"GUID:\s*([0-9a-fA-F-]{36})\s*\(([^)]+)\)")
GAME_MODE_KEY = r"Software\Microsoft\GameBar"
GAME_MODE_VALUE = "AutoGameModeEnabled"


def _require_windows():
    if not c.IS_WINDOWS:
        raise ValueError("Modes only work on Windows.")


# --- power plan -----------------------------------------------------------------------

def list_schemes():
    """[{"name": ..., "guid": ...}] for every power plan Windows knows about on this PC, in its own casing."""
    if not c.IS_WINDOWS:
        return []
    return [{"name": name.strip(), "guid": guid} for guid, name in SCHEME_LINE.findall(c.run(["powercfg", "/list"]))]


def _scheme_guid(name):
    return next((s["guid"] for s in list_schemes() if s["name"].lower() == (name or "").lower()), None)


def active_scheme():
    """(guid, name) of the plan in use right now, or (None, None)."""
    if not c.IS_WINDOWS:
        return None, None
    match = SCHEME_LINE.search(c.run(["powercfg", "/getactivescheme"]))
    return (match.group(1), match.group(2)) if match else (None, None)


def set_scheme(guid):
    _require_windows()
    subprocess.run(["powercfg", "/setactive", guid], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# --- Game Mode --------------------------------------------------------------------------

def get_game_mode():
    if not c.IS_WINDOWS:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GAME_MODE_KEY) as key:
            return bool(winreg.QueryValueEx(key, GAME_MODE_VALUE)[0])
    except OSError:
        return True  # Windows default is on when the key hasn't been created yet


def set_game_mode(enabled):
    _require_windows()
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, GAME_MODE_KEY) as key:
        winreg.SetValueEx(key, GAME_MODE_VALUE, 0, winreg.REG_DWORD, 1 if enabled else 0)


# --- apps ---------------------------------------------------------------------------------

def is_running(name):
    names = {n.lower() for n in c.process_names().values()}
    return name.lower() in names


def close_app(name):
    _require_windows()
    subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def open_app(target):
    _require_windows()
    import os
    try:
        os.startfile(target)  # resolves a path, a URL, or a name Windows can find on PATH
    except OSError as err:
        raise ValueError(f"Couldn't open \"{target}\": {err.strerror or err}")


# --- config ---------------------------------------------------------------------------

def _find_mode(mode_id):
    modes = paths.load_settings()["modes"]
    mode = next((m for m in modes if m["id"] == mode_id), None)
    if not mode:
        raise ValueError("Unknown mode.")
    return mode


def save_modes(modes):
    if not isinstance(modes, list) or not modes:
        raise ValueError("Expected a list of modes.")
    clean = []
    for m in modes:
        if not isinstance(m, dict) or not m.get("id") or not m.get("name"):
            raise ValueError("Each mode needs an id and a name.")
        clean.append({
            "id": str(m["id"])[:30], "name": str(m["name"])[:40],
            "powerPlan": (m.get("powerPlan") or None),
            "gameMode": m.get("gameMode") if m.get("gameMode") in (True, False) else None,
            "closeApps": [str(a)[:100] for a in (m.get("closeApps") or []) if str(a).strip()][:20],
            "openApps": [str(a)[:200] for a in (m.get("openApps") or []) if str(a).strip()][:20],
        })
    paths.save_settings(modes=clean)
    return clean


def state():
    settings = paths.load_settings()
    _, active_name = active_scheme()
    return {
        "supported": c.IS_WINDOWS, "modes": settings["modes"], "modeState": settings["modeState"],
        "schemes": [s["name"] for s in list_schemes()],
        "activePlan": active_name, "gameMode": get_game_mode(),
    }


# --- preview / apply / revert -----------------------------------------------------------

def preview(mode_id):
    mode = _find_mode(mode_id)
    changes = []
    if mode.get("powerPlan"):
        _, current_name = active_scheme()
        if current_name and current_name.lower() != mode["powerPlan"].lower():
            changes.append(f"Power plan: {current_name} → {mode['powerPlan']}")
        elif not current_name:
            changes.append(f"Power plan → {mode['powerPlan']}")
    if mode.get("gameMode") is not None:
        current = get_game_mode()
        if current != mode["gameMode"]:
            changes.append(f"Game Mode: {'on' if current else 'off'} → {'on' if mode['gameMode'] else 'off'}")
    running_to_close = [a for a in mode.get("closeApps") or [] if is_running(a)]
    if running_to_close:
        changes.append(f"Close: {', '.join(running_to_close)}")
    if mode.get("openApps"):
        changes.append(f"Open: {', '.join(mode['openApps'])}")
    if not changes:
        changes.append("Nothing to change -- already set up this way.")
    return {"name": mode["name"], "changes": changes}


def apply(mode_id):
    _require_windows()
    mode = _find_mode(mode_id)
    mode_state = dict(paths.load_settings()["modeState"])
    changes = []

    # Remember how things were before the FIRST mode switch, so "Back to normal" has a baseline.
    if mode_state.get("active") is None:
        guid, name = active_scheme()
        mode_state["previous"] = {"schemeGuid": guid, "schemeName": name, "gameMode": get_game_mode()}

    if mode.get("powerPlan"):
        guid = _scheme_guid(mode["powerPlan"])
        if guid:
            set_scheme(guid)
            changes.append(f"Power plan set to {mode['powerPlan']}")
        else:
            changes.append(f"Power plan \"{mode['powerPlan']}\" wasn't found on this PC, so it was left alone")

    if mode.get("gameMode") is not None:
        set_game_mode(mode["gameMode"])
        changes.append(f"Game Mode turned {'on' if mode['gameMode'] else 'off'}")

    for name in mode.get("closeApps") or []:
        if is_running(name):
            close_app(name)
            changes.append(f"Closed {name}")
    for target in mode.get("openApps") or []:
        try:
            open_app(target)
            changes.append(f"Opened {target}")
        except ValueError as err:
            changes.append(str(err))

    mode_state["active"] = mode_id
    mode_state["appliedAt"] = paths.now_iso()
    paths.save_settings(modeState=mode_state)
    return {"name": mode["name"], "changes": changes}


def revert():
    _require_windows()
    settings = paths.load_settings()
    mode_state = settings["modeState"]
    previous = mode_state.get("previous")
    if not previous:
        raise ValueError("No mode is active.")
    changes = []
    if previous.get("schemeGuid"):
        set_scheme(previous["schemeGuid"])
        changes.append(f"Power plan back to {previous.get('schemeName') or 'what it was'}")
    if previous.get("gameMode") is not None:
        set_game_mode(previous["gameMode"])
        changes.append(f"Game Mode back to {'on' if previous['gameMode'] else 'off'}")
    changes.append("Apps that were closed or opened aren't restored -- Windows doesn't remember what was open before.")
    paths.save_settings(modeState={"active": None, "previous": None, "appliedAt": None})
    return {"changes": changes}
