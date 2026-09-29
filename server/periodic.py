"""
A background check that runs on a timer, and can also be asked to run right now.

Used by the Windows health, events and tune-up monitors. "Check again" in the
dashboard calls run_now_and_wait(), which wakes the loop, waits for that run to
finish (or a timeout), and returns, so the Advisor can re-evaluate immediately.
"""

import threading
import time


class PeriodicMonitor:
    interval = 300  # seconds between regular runs
    name = "check"

    def __init__(self):
        self.latest = None
        self.checked_at = None  # time.time() of the last successful run
        self.error = None
        self._wake = threading.Event()
        self._done = threading.Condition()
        self._runs = 0

    # Subclasses implement collect() -> result or None (None = the check failed).
    def collect(self):
        raise NotImplementedError

    def enabled(self):
        return True

    def start(self):
        if self.enabled():
            threading.Thread(target=self._loop, daemon=True, name=self.name).start()

    def _loop(self):
        while True:
            try:
                result = self.collect()
                if result is not None:
                    self.latest = result
                    self.checked_at = time.time()
                    self.error = None
                else:
                    self.error = "returned no data"
                    print(f"[matrix] {self.name} check returned no data.")
            except Exception as err:  # keep the loop alive whatever happens
                self.error = str(err)
                print(f"[matrix] {self.name} check failed: {err}")
            with self._done:
                self._runs += 1
                self._done.notify_all()
            self._wake.wait(self.interval)
            self._wake.clear()

    def run_now_and_wait(self, timeout=120):
        """Start a run immediately and wait until it completes. Returns True if it finished in time."""
        if not self.enabled():
            return False
        with self._done:
            target = self._runs + 1
            self._wake.set()
            end = time.time() + timeout
            while self._runs < target:
                remaining = end - time.time()
                if remaining <= 0:
                    return False
                self._done.wait(remaining)
        return True
