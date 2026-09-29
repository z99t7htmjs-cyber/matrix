"""
Matrix's memory: a small SQLite database in the data folder (history.db).

  samples     one row per minute: CPU, memory, GPU, GPU temperature, network speed
  devices     every device ever seen: first seen, last seen, last IP
  presence    which hours each device was online (for "usually online" patterns)
  timeline    things that happened: devices joining, crashes, alerts raised and
              resolved, repairs detected, AI notes
  alerts      the state of each Advisor item: active, snoozed, kept, acknowledged, resolved
  plan_steps  troubleshooting steps done (detected automatically or marked by you)
  ai_notes    short explanations written by the local AI

Old data is trimmed automatically: samples after 90 days, presence after 60,
timeline after a year.
"""

import json
import sqlite3
import threading
import time

from paths import DATA_DIR

DB_FILE = DATA_DIR / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts INTEGER PRIMARY KEY, cpu REAL, memory REAL, gpu REAL, gpu_temp REAL, net_in REAL, net_out REAL);
CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY, first_seen INTEGER, last_seen INTEGER, last_ip TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS presence (
    mac TEXT, hour INTEGER, PRIMARY KEY (mac, hour));
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT, title TEXT, detail TEXT, ref TEXT);
CREATE INDEX IF NOT EXISTS timeline_ts ON timeline (ts);
CREATE TABLE IF NOT EXISTS alerts (
    key TEXT PRIMARY KEY, status TEXT, fingerprint TEXT, title TEXT, urgency TEXT,
    raised_at INTEGER, changed_at INTEGER, until INTEGER, seen_absent INTEGER DEFAULT 0, kind TEXT);
CREATE TABLE IF NOT EXISTS plan_steps (
    plan TEXT, step TEXT, done_at INTEGER, source TEXT, detail TEXT, PRIMARY KEY (plan, step));
CREATE TABLE IF NOT EXISTS plans (
    plan TEXT PRIMARY KEY, started_at INTEGER);
CREATE TABLE IF NOT EXISTS ai_notes (
    key TEXT PRIMARY KEY, ts INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS snapshots (
    date TEXT PRIMARY KEY, ts INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, text TEXT);
"""

KEEP_SAMPLES_DAYS = 90
KEEP_PRESENCE_DAYS = 60
KEEP_TIMELINE_DAYS = 365
KEEP_SNAPSHOTS_DAYS = 120


class History:
    def __init__(self, path=DB_FILE):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()
        self._last_trim = 0

    def _run(self, sql, params=(), many=False):
        with self.lock:
            cur = self.db.executemany(sql, params) if many else self.db.execute(sql, params)
            self.db.commit()
            return cur

    def _all(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def _one(self, sql, params=()):
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # --- performance samples -------------------------------------------------------

    def add_sample(self, ts, cpu, memory, gpu, gpu_temp, net_in, net_out):
        self._run("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)",
                  (int(ts), cpu, memory, gpu, gpu_temp, net_in, net_out))
        self._trim()

    def average(self, field, start_ts, end_ts):
        """Average of one samples column (cpu, memory, gpu, gpu_temp) over a fixed time range."""
        if field not in ("cpu", "memory", "gpu", "gpu_temp"):
            raise ValueError("Unknown field.")
        row = self._one(f"SELECT AVG({field}) AS v FROM samples WHERE ts >= ? AND ts < ?", (int(start_ts), int(end_ts)))
        return row["v"] if row and row["v"] is not None else None

    def series(self, seconds, buckets=240):
        """Averages (and peaks for CPU) in evenly sized time buckets over the last `seconds`."""
        now = int(time.time())
        start = now - seconds
        size = max(60, seconds // buckets)
        rows = self._all(
            """SELECT (ts - ?) / ? AS b, MIN(ts) AS t, AVG(cpu) AS cpu, MAX(cpu) AS cpu_max,
                      AVG(memory) AS memory, AVG(gpu) AS gpu, MAX(gpu_temp) AS gpu_temp,
                      AVG(net_in) AS net_in, AVG(net_out) AS net_out
               FROM samples WHERE ts >= ? GROUP BY b ORDER BY b""",
            (start, size, start),
        )
        return {"start": start, "end": now, "bucketSeconds": size, "points": rows}

    # --- devices ----------------------------------------------------------------------

    def record_devices(self, nodes):
        """Remember every online device; returns MACs seen for the first time ever."""
        now = int(time.time())
        hour = now // 3600 * 3600
        new = []
        with self.lock:
            for n in nodes:
                mac = n.get("mac")
                if not mac or n.get("status") != "online":
                    continue
                row = self.db.execute("SELECT first_seen FROM devices WHERE mac=?", (mac,)).fetchone()
                if row is None:
                    new.append(n)
                    self.db.execute("INSERT INTO devices VALUES (?,?,?,?,?)", (mac, now, now, n.get("ip"), n.get("name")))
                else:
                    self.db.execute("UPDATE devices SET last_seen=?, last_ip=?, name=? WHERE mac=?",
                                    (now, n.get("ip"), n.get("name"), mac))
                self.db.execute("INSERT OR IGNORE INTO presence VALUES (?,?)", (mac, hour))
            self.db.commit()
        return new

    def device_count(self):
        return self._one("SELECT COUNT(*) AS n FROM devices")["n"]

    def device_history(self, mac):
        info = self._one("SELECT * FROM devices WHERE mac=?", (mac,))
        hours = [r["hour"] for r in self._all("SELECT hour FROM presence WHERE mac=? ORDER BY hour", (mac,))]
        return info, hours

    # --- timeline ---------------------------------------------------------------------

    def log(self, kind, title, detail="", ref="", ts=None):
        self._run("INSERT INTO timeline (ts, kind, title, detail, ref) VALUES (?,?,?,?,?)",
                  (int(ts or time.time()), kind, title, detail, ref))

    def timeline(self, limit=200, since=None):
        if since:
            return self._all("SELECT * FROM timeline WHERE ts > ? ORDER BY ts DESC LIMIT ?", (int(since), limit))
        return self._all("SELECT * FROM timeline ORDER BY ts DESC LIMIT ?", (limit,))

    def logged(self, kind, ref):
        return self._one("SELECT id FROM timeline WHERE kind=? AND ref=?", (kind, ref)) is not None

    def count_timeline(self, kind, ref):
        row = self._one("SELECT COUNT(*) AS n FROM timeline WHERE kind=? AND ref=?", (kind, ref))
        return row["n"] if row else 0

    # --- alert states -----------------------------------------------------------------

    def alert_states(self):
        return {r["key"]: r for r in self._all("SELECT * FROM alerts")}

    def save_alert(self, a):
        self._run(
            """INSERT OR REPLACE INTO alerts (key, status, fingerprint, title, urgency, raised_at, changed_at, until, seen_absent, kind)
               VALUES (:key, :status, :fingerprint, :title, :urgency, :raised_at, :changed_at, :until, :seen_absent, :kind)""",
            {"kind": None, **a},
        )

    # --- plans ------------------------------------------------------------------------

    def plan_started(self, plan):
        row = self._one("SELECT started_at FROM plans WHERE plan=?", (plan,))
        return row["started_at"] if row else None

    def start_plan(self, plan, ts):
        self._run("INSERT OR IGNORE INTO plans VALUES (?,?)", (plan, int(ts)))

    def end_plan(self, plan):
        self._run("DELETE FROM plans WHERE plan=?", (plan,))
        self._run("DELETE FROM plan_steps WHERE plan=?", (plan,))

    def plan_steps(self, plan):
        return {r["step"]: r for r in self._all("SELECT * FROM plan_steps WHERE plan=?", (plan,))}

    def mark_step(self, plan, step, done_at, source, detail=""):
        self._run("INSERT OR REPLACE INTO plan_steps VALUES (?,?,?,?,?)", (plan, step, int(done_at), source, detail))

    def unmark_step(self, plan, step):
        self._run("DELETE FROM plan_steps WHERE plan=? AND step=?", (plan, step))

    # --- AI notes ---------------------------------------------------------------------

    def ai_note(self, key):
        return self._one("SELECT * FROM ai_notes WHERE key=?", (key,))

    def save_ai_note(self, key, text):
        self._run("INSERT OR REPLACE INTO ai_notes VALUES (?,?,?)", (key, int(time.time()), text))

    def ai_notes_today(self):
        return self._one("SELECT COUNT(*) AS n FROM ai_notes WHERE ts > ?", (int(time.time()) - 86400,))["n"]

    # --- daily snapshots ("what changed?") ---------------------------------------------

    def save_snapshot(self, date, data):
        self._run("INSERT OR REPLACE INTO snapshots (date, ts, data) VALUES (?,?,?)", (date, int(time.time()), dumps(data)))

    def snapshots_before(self, date, limit=1):
        """The most recent snapshot(s) strictly before `date` (a 'YYYY-MM-DD' string), newest first."""
        rows = self._all("SELECT * FROM snapshots WHERE date < ? ORDER BY date DESC LIMIT ?", (date, limit))
        return [{"date": r["date"], **json.loads(r["data"])} for r in rows]

    # --- weekly AI digest ---------------------------------------------------------------

    def save_digest(self, text):
        self._run("INSERT INTO digests (ts, text) VALUES (?,?)", (int(time.time()), text))

    def latest_digest(self):
        return self._one("SELECT * FROM digests ORDER BY ts DESC LIMIT 1")

    # --- housekeeping -----------------------------------------------------------------

    def _trim(self):
        now = time.time()
        if now - self._last_trim < 3600:
            return
        self._last_trim = now
        self._run("DELETE FROM samples WHERE ts < ?", (int(now - KEEP_SAMPLES_DAYS * 86400),))
        self._run("DELETE FROM presence WHERE hour < ?", (int(now - KEEP_PRESENCE_DAYS * 86400),))
        self._run("DELETE FROM timeline WHERE ts < ?", (int(now - KEEP_TIMELINE_DAYS * 86400),))
        self._run("DELETE FROM snapshots WHERE ts < ?", (int(now - KEEP_SNAPSHOTS_DAYS * 86400),))

    def size_mb(self):
        try:
            return round(DB_FILE.stat().st_size / 1e6, 1)
        except OSError:
            return 0


def presence_summary(hours):
    """Turn online hours into plain words: when a device is usually around."""
    if not hours:
        return None
    from datetime import datetime

    days = {}
    by_hour = [0] * 24
    by_weekday = [0] * 7
    for h in hours:
        dt = datetime.fromtimestamp(h)
        days.setdefault(dt.date(), 0)
        days[dt.date()] += 1
        by_hour[dt.hour] += 1
        by_weekday[dt.weekday()] += 1
    total_days = len(days)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def label(hour):
        return datetime(2000, 1, 1, hour % 24).strftime("%I %p").lstrip("0")

    # Hours when the device is online at least half as often as its busiest hour,
    # joined into ranges ("6 PM – 1 AM"), wrapping around midnight.
    peak = max(by_hour)
    active = [by_hour[i] >= peak * 0.5 for i in range(24)]
    ranges = []
    if all(active):
        usual = "around the clock"
    else:
        start = next(i for i in range(24) if not active[i])  # begin scanning just after a quiet hour
        run = None
        for k in range(1, 25):
            i = (start + k) % 24
            if active[i] and run is None:
                run = i
            elif not active[i] and run is not None:
                ranges.append((run, i))
                run = None
        if run is not None:
            ranges.append((run, start))
        ranges.sort(key=lambda r: sum(by_hour[(r[0] + j) % 24] for j in range((r[1] - r[0]) % 24 or 24)), reverse=True)
        usual = ", ".join(f"{label(a)} – {label(b)}" for a, b in ranges[:2])

    return {
        "daysSeen": total_days,
        "hoursSeen": len(hours),
        "byHour": by_hour,
        "byWeekday": by_weekday,
        "usualHours": usual if len(hours) >= 6 else None,
        "busiestDay": names[max(range(7), key=lambda i: by_weekday[i])] if total_days >= 3 else None,
        "alwaysOn": total_days >= 2 and len(hours) >= total_days * 20,
    }


def dumps(value):
    return json.dumps(value, default=str)
