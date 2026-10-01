"""
Auto-switch power mode when the laptop is plugged in or unplugged.

Off by default -- turning on "Auto-switch power mode" in Settings is the one
thing in Matrix that changes something without a click in the moment, so it's
opt-in, and every switch it makes still gets announced the same way a manual
mode switch would (a notification, plus a line in the timeline). It reuses
the existing Modes apply() machinery -- two plain Modes named "Desktop" and
"Locked-down" (see paths.POWER_SWITCH_MODES) -- rather than a parallel system,
so Rob can still rename or edit either one in Settings like any other mode.

State is kept in memory only, not persisted: the first reading after startup
just records the current plugged/unplugged state as a baseline without
switching anything (so Matrix never fires a "you just plugged in" notice the
moment it starts up on a laptop that was already plugged in). Re-applying the
same mode twice is harmless -- modes.apply() is idempotent -- so there's
nothing to lose by not remembering this across restarts.
"""

import modes
import paths

DESKTOP_MODE_ID = "desktop"
LOCKED_DOWN_MODE_ID = "locked-down"


class PowerSwitch:
    def __init__(self):
        self._last_plugged = None  # None = haven't seen a reading yet

    def tick(self, system_snapshot, notify):
        """Call on every evaluate tick with SystemMonitor.latest. Fires at most one
        mode switch per actual plug/unplug transition. `notify(title, message)` is
        called only when a switch actually happens."""
        if not paths.load_settings().get("autoSwitchPower"):
            self._last_plugged = None  # re-arm so turning this on doesn't switch off a stale reading
            return
        battery = (system_snapshot or {}).get("battery")
        if not battery or battery.get("plugged") is None:
            return  # desktop PC, or battery info not available this tick
        plugged = bool(battery["plugged"])
        if self._last_plugged is None:
            self._last_plugged = plugged  # first reading: just establish the baseline
            return
        if plugged == self._last_plugged:
            return
        self._last_plugged = plugged
        mode_id = DESKTOP_MODE_ID if plugged else LOCKED_DOWN_MODE_ID
        try:
            result = modes.apply(mode_id)
        except ValueError:
            return  # the mode was renamed/removed in Settings; nothing to apply
        label = "Plugged in" if plugged else "Unplugged"
        notify(f"Matrix: {label} -> {result['name']} mode", "; ".join(result["changes"]) or "Nothing to change.")
