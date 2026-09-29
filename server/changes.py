"""
"What changed?": a daily snapshot of settings that matter, and a diff
against the last snapshot before today.

Snapshots come from whatever the Tune-up check already reads every 30
minutes (installed apps, startup apps, running services, power plan, Game
Mode, Storage Sense), so nothing extra is collected just for this. Old
snapshots are kept for 120 days (history.py) and trimmed automatically.

Effects: when apps were newly installed since the last snapshot, and
average memory use over the last 3 days is well above the 3 days before
that, this says so ("memory use is up 30% since Tuesday, when X was
installed"). It's a correlation over roughly the same window, not a
guarantee that one caused the other.
"""

import time
from datetime import date, datetime

EFFECT_MIN_PERCENT = 15
EFFECT_MIN_BASELINE = 5  # ignore tiny baselines, where "up 15%" isn't meaningful


def today_str(ts=None):
    return date.fromtimestamp(ts or time.time()).isoformat()


def build_snapshot(tuneup):
    """A compact, comparable slice of Tune-up's latest reading, or None if it hasn't checked yet."""
    if not tuneup or not tuneup.get("checked"):
        return None
    return {
        "powerPlan": tuneup.get("powerPlan"),
        "gameMode": tuneup.get("gameMode"),
        "storageSense": tuneup.get("storageSense"),
        "startupApps": tuneup.get("startupNames") or [],
        "installedApps": tuneup.get("installedNames") or [],
        "services": tuneup.get("services") or [],
    }


def _list_diff(sections, label, before, after):
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    if added or removed:
        sections.append({"label": label, "added": added, "removed": removed, "changed": None})


def _fmt(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _effect(history, prev, snapshot):
    added_apps = sorted(set(snapshot.get("installedApps") or []) - set(prev.get("installedApps") or []))
    if not added_apps:
        return None
    now = time.time()
    after = history.average("memory", now - 3 * 86400, now)
    before = history.average("memory", now - 10 * 86400, now - 7 * 86400)
    if after is None or before is None or before < EFFECT_MIN_BASELINE:
        return None
    change = (after - before) / before * 100
    if abs(change) < EFFECT_MIN_PERCENT:
        return None
    direction = "up" if change > 0 else "down"
    label = added_apps[0] if len(added_apps) == 1 else f"{added_apps[0]} and {len(added_apps) - 1} other app(s)"
    return f"Memory use is {direction} {abs(change):.0f}% over the last 3 days, around when {label} was installed."


def diff(history, snapshot, today=None):
    """Save today's snapshot and compare it with the one before it. None if there's nothing to compare yet."""
    if snapshot is None:
        return None
    today = today or today_str()
    history.save_snapshot(today, snapshot)
    earlier = history.snapshots_before(today, limit=1)
    if not earlier:
        return None
    prev = earlier[0]

    sections = []
    _list_diff(sections, "Installed apps", prev.get("installedApps") or [], snapshot.get("installedApps") or [])
    _list_diff(sections, "Startup apps", prev.get("startupApps") or [], snapshot.get("startupApps") or [])
    _list_diff(sections, "Running services", prev.get("services") or [], snapshot.get("services") or [])
    for key, label in (("powerPlan", "Power plan"), ("gameMode", "Game Mode"), ("storageSense", "Storage Sense")):
        if prev.get(key) != snapshot.get(key):
            sections.append({"label": label, "added": [], "removed": [],
                             "changed": f"{_fmt(prev.get(key))} → {_fmt(snapshot.get(key))}"})

    return {"since": prev["date"], "sections": sections, "effect": _effect(history, prev, snapshot)}
