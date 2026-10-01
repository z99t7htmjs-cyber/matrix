"""
Wake-source log: plain background data collection for the mouse-waking-the-
house problem. No UI yet -- Rob asked for just the log, "nothing flashy,"
so this is raw material for a future conversation about the actual fix
(likely something in the ASUS BIOS), not a feature with its own card.

There's no clean, documented Windows API that fires an event the moment the
PC wakes from sleep that a plain background script can subscribe to. What
this does instead: poll every WAKE_CHECK_SECONDS, and if the actual gap
since the last poll is much bigger than that interval, the PC was almost
certainly asleep in between (a running thread can't skip ticks on its own).
The moment that's noticed, ask Windows what actually caused the wake
(`powercfg /lastwake`, no admin needed) and save it. This can occasionally
misfire (a long GC pause, Matrix's own process briefly starved of CPU) but
the cost of a false entry here is nothing -- it's a log, not an alert.
"""

import json
import time
from datetime import datetime, timezone

import collectors as c
from paths import DATA_DIR, write_json_atomic
from periodic import PeriodicMonitor

WAKE_LOG_FILE = DATA_DIR / "wake_history.json"

WAKE_CHECK_SECONDS = 20
# Comfortably more than one missed tick's worth of normal scheduling jitter, but far less
# than any real sleep -- a laptop doesn't nod off for 90 seconds and wake back up on its own.
GAP_THRESHOLD_SECONDS = 90
MAX_HISTORY = 300


def _load():
    try:
        data = json.loads(WAKE_LOG_FILE.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        return list(entries) if isinstance(entries, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(entries):
    write_json_atomic(WAKE_LOG_FILE, {"entries": entries[-MAX_HISTORY:]})


class WakeLogMonitor(PeriodicMonitor):
    name = "Wake log"
    interval = WAKE_CHECK_SECONDS

    def __init__(self):
        super().__init__()
        self._entries = _load()
        self._last_tick = None

    def enabled(self):
        return c.IS_WINDOWS

    def collect(self):
        now = time.time()
        gap = (now - self._last_tick) if self._last_tick is not None else 0
        self._last_tick = now
        if gap > GAP_THRESHOLD_SECONDS:
            self._record(gap)
        return {"entries": len(self._entries)}

    def _record(self, asleep_seconds):
        source = c.run(["powercfg", "/lastwake"], timeout=10).strip() or "powercfg returned nothing"
        self._entries.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "asleepSeconds": round(asleep_seconds),
            "source": source[:2000],
        })
        _save(self._entries)

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at, timezone.utc).isoformat() if self.checked_at else None
        return {"supported": c.IS_WINDOWS, "checkedAt": checked, "recent": self._entries[-20:]}
