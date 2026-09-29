"""
Idle-temperature trend: a proxy for dust buildup / degraded cooling.

Matrix has no fan-RPM sensor to read. Windows exposes no standard API for
that, and the vendor SDKs that do (Armoury Crate's own telemetry) aren't
something Matrix depends on -- adding one would mean bundling ASUS's own
driver-level library just for a number. What IS already available is the
GPU temperature system.py samples every couple of seconds. The idea: watch
for that temperature specifically during windows where the PC is doing
basically nothing (low CPU and GPU load), keep the coolest reading seen
each day, and watch whether that idle baseline creeps up over weeks. Dust
packed into the intake and fins raises resting temperature well before it's
bad enough to throttle performance or trip a "too hot" alert, so this can
give an earlier signal than either of those.

This is a proxy, not a real dust sensor. Room temperature, where the laptop
sits (desk vs. lap vs. under a blanket), and driver or firmware changes can
all move idle temps too -- the report to the user says so, and this never
claims to know the cause, only that resting temperature has risen.
"""

import json
from datetime import datetime, timezone

from paths import DATA_DIR, write_json_atomic
from periodic import PeriodicMonitor

THERMAL_HISTORY_FILE = DATA_DIR / "thermal_history.json"

CHECK_EVERY_SECONDS = 300  # look every 5 min for an idle window worth sampling
IDLE_CPU_MAX = 15  # percent
IDLE_GPU_MAX = 5  # percent
MAX_HISTORY_DAYS = 180  # about 6 months of daily readings; old enough to mean something, not unbounded
MIN_DAYS_FOR_TREND = 14  # need at least two weeks of idle samples before saying anything at all
RISE_ATTENTION_C = 8
RISE_CRITICAL_C = 12


def _load_history():
    try:
        data = json.loads(THERMAL_HISTORY_FILE.read_text(encoding="utf-8"))
        days = data.get("days") if isinstance(data, dict) else None
        return dict(days) if isinstance(days, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_history(days):
    write_json_atomic(THERMAL_HISTORY_FILE, {"days": days})


class ThermalTrendMonitor(PeriodicMonitor):
    """Watches for a rising idle GPU temperature over weeks -- a dust/cooling proxy.

    Takes the live SystemMonitor so it can read the CPU/GPU load and GPU temp
    that's already being sampled every couple of seconds, rather than running
    any check of its own -- this only decides when a sample counts as "idle"
    and remembers the coolest one seen each day.
    """

    name = "Thermal trend"
    interval = CHECK_EVERY_SECONDS

    def __init__(self, system_monitor):
        super().__init__()
        self._system = system_monitor
        self._history = _load_history()

    def enabled(self):
        return self._system.available and bool(self._system.nvidia_smi)

    def collect(self):
        sample = self._system.latest
        if sample:
            gpus = sample.get("gpus") or []
            cpu = sample.get("cpu") or {}
            if gpus and gpus[0].get("tempC") is not None:
                cpu_usage = cpu.get("usage")
                gpu_usage = gpus[0].get("usage")
                idle = (cpu_usage is not None and cpu_usage <= IDLE_CPU_MAX and
                        gpu_usage is not None and gpu_usage <= IDLE_GPU_MAX)
                if idle:
                    self._record(gpus[0]["tempC"])
        return self._trend()

    def _record(self, temp_c):
        today = datetime.now().strftime("%Y-%m-%d")
        current = self._history.get(today)
        if current is not None and temp_c >= current:
            return  # already have an equal-or-cooler reading for today
        self._history[today] = temp_c
        if len(self._history) > MAX_HISTORY_DAYS:
            for old_day in sorted(self._history)[:len(self._history) - MAX_HISTORY_DAYS]:
                del self._history[old_day]
        _save_history(self._history)

    def _trend(self):
        days = sorted(self._history)
        samples = [self._history[d] for d in days]
        result = {
            "supported": True,
            "sampleDays": len(samples),
            "minDaysNeeded": MIN_DAYS_FOR_TREND,
            "latestIdleTempC": samples[-1] if samples else None,
            "latestIdleDate": days[-1] if days else None,
            "hasEnoughHistory": len(samples) >= MIN_DAYS_FOR_TREND,
            "baselineC": None,
            "recentC": None,
            "risenC": None,
        }
        # Split chronologically in half and compare medians: as more days pile up, "older"
        # keeps growing too, so this is always comparing against everything on record, not a
        # fixed window that ages out of relevance.
        if result["hasEnoughHistory"]:
            mid = len(samples) // 2
            older, newer = sorted(samples[:mid]), sorted(samples[mid:])
            result["baselineC"] = older[len(older) // 2]
            result["recentC"] = newer[len(newer) // 2]
            result["risenC"] = round(result["recentC"] - result["baselineC"], 1)
        return result

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at, timezone.utc).isoformat() if self.checked_at else None
        if not self.enabled():
            return {"supported": False, "checkedAt": checked}
        return {"checkedAt": checked, **(self.latest or self._trend())}
