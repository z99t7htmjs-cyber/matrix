"""
Matrix local server.

  * Serves the Matrix dashboard and watches this PC, Windows and the network
    in background threads, remembering history in a local database.
  * Every 10 seconds the Advisor re-evaluates everything; alerts.py keeps
    track of what you've done about each item.

  GET  /api/state        everything the dashboard shows
  GET  /api/settings     auto-start, data folder, version
  GET  /api/history      performance history (?range=30m|24h|7d|30d)
  GET  /api/timeline     what happened (?since=unix time)
  GET  /api/device       one device's history (?mac=…)
  GET  /api/diagnostics  plain-text report for troubleshooting
  POST /api/devices      name, forget, ignore or trust devices
  POST /api/identify     run a few light checks on one device
  POST /api/alerts       acknowledge, snooze, keep or restore an Advisor item
  POST /api/plan         mark a troubleshooting step done (or not)
  POST /api/check        re-run a check now ("Check again")
  POST /api/open         open a Windows settings page or tool (fixed list, see desktop.py)
  POST /api/screenshot   copy a screenshot of the Matrix window to the clipboard
  POST /api/settings     change auto-start
  POST /api/chat         Ask Matrix: stream an answer from the local AI (Ollama)
  POST /api/quit         stop Matrix

It only listens on 127.0.0.1 and only answers requests addressed to
localhost, so neither other devices nor other websites can use it. Checks are
read-only; Matrix writes only its data folder and, if you turn on auto-start,
one per-user "Run" entry.

Normally started by the Start menu shortcut. From a terminal:
    python server/matrix_server.py              run here, logging to the terminal
    python server/matrix_server.py --open       run in the background and open the app window
    python server/matrix_server.py --port 8081 --model gemma3:4b
"""

import argparse
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import advisor
import ai
import changes
import collectors as c
import desktop
import diagnostics
import digest
import identify
import modes
import network
import paths
import plans
from alerts import AlertManager
from drive_health import DriveHealthMonitor
from history import History, presence_summary
from network import NetworkBuilder
from proactive import Explainer
from system import SystemMonitor
from thermal_trend import ThermalTrendMonitor
from tuneup import TuneupMonitor
from update_check import UpdateCheckMonitor
from windows_events import EventsMonitor
from windows_health import HealthMonitor

# Background cadence for the passive network rescan -- who's on your network realistically
# doesn't change multiple times a minute, and every scan spawns five separate system
# commands (route, arp, netstat x2, tasklist). Anything that needs it sooner (an action in
# the UI, "Check again") calls rescan_and_wait() directly and isn't slowed by this at all.
NETWORK_EVERY_SECONDS = 20
EVALUATE_EVERY_SECONDS = 10
SAMPLE_EVERY_SECONDS = 60
DIGEST_CHECK_EVERY_SECONDS = 3600
MAX_LOG_BYTES = 1_000_000
HISTORY_RANGES = {"30m": 1800, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}


class Monitor:
    """Owns the background watchers, the history, and the Advisor's lifecycle."""

    def __init__(self):
        self.network = NetworkBuilder()
        self.system = SystemMonitor()
        self.health = HealthMonitor()
        self.events = EventsMonitor()
        self.tuneup = TuneupMonitor()
        self.drives = DriveHealthMonitor()
        self.thermal = ThermalTrendMonitor(self.system)
        self.updates = UpdateCheckMonitor()
        self.history = History()
        self.explainer = Explainer(self.history, self.base_state, lambda: options["model"])
        self.alerts = AlertManager(self.history, notify=self._notify, explain=self.explainer.request)
        self.tray = None
        self.network_state = {"nodes": [], "links": []}
        self.network_at = None
        self.network_runs = 0
        self.rescan = threading.Event()  # set to rebuild the map right away
        self.evaluated = {"advice": [], "handled": [], "resolved": [], "plans": {}}
        self.eval_lock = threading.Lock()
        self.last_sample = 0
        self.changes = None
        self.last_snapshot_date = None

    def start(self):
        self.history.log("matrix", f"Matrix {paths.VERSION} started", "", ref=f"start:{int(time.time())}")
        for watcher in (self.network, self.system, self.health, self.events, self.tuneup, self.drives, self.thermal, self.updates, self.explainer):
            watcher.start()
        threading.Thread(target=self._network_loop, daemon=True, name="network").start()
        threading.Thread(target=self._evaluate_loop, daemon=True, name="advisor").start()
        threading.Thread(target=self._digest_loop, daemon=True, name="digest").start()

    # --- network --------------------------------------------------------------------

    def _network_loop(self):
        while True:
            try:
                nodes = self.network.build()
                self.network_state = nodes
                self.network_at = datetime.now(timezone.utc).isoformat()
                self._remember_devices(nodes["nodes"])
                self.network_runs += 1
            except Exception as err:  # keep watching even if one scan fails
                print(f"[matrix] Network scan failed: {err}")
            self.rescan.wait(NETWORK_EVERY_SECONDS)
            self.rescan.clear()

    def _remember_devices(self, nodes):
        first_ever = self.history.device_count() == 0
        new = self.history.record_devices([n for n in nodes if n["id"] != "internet"])
        if first_ever and new:
            self.history.log("device", f"Matrix started remembering {len(new)} devices", "", ref="devices:first")
            return
        for n in new:
            self.history.log("device", f"New device joined: {n['name']}",
                             f"{n.get('ip') or 'no IP'} · {n.get('vendor') or 'unknown maker'}", ref=f"device:{n['mac']}")

    def rescan_and_wait(self, timeout=20):
        target = self.network_runs + 1
        self.rescan.set()
        end = time.time() + timeout
        while self.network_runs < target and time.time() < end:
            time.sleep(0.2)

    # --- state ------------------------------------------------------------------------

    def base_state(self):
        return {
            "network": self.network_state,
            "system": self.system.snapshot(),
            "health": self.health.snapshot(),
            "events": self.events.snapshot(),
            "tuneup": self.tuneup.snapshot(),
            "drives": self.drives.snapshot(),
            "updateCheck": self.updates.snapshot(),
            "thermalTrend": self.thermal.snapshot(),
            "meta": {
                "version": paths.VERSION,
                "vendorDb": self.network.vendors.status,
                "networkUpdatedAt": self.network_at,
                "baselineAt": paths.load_settings().get("baselineAt"),
                "platform": "windows" if c.IS_WINDOWS else "other",
                "personaEnabled": paths.load_settings().get("personaEnabled", True),
                "livingLook": paths.load_settings().get("livingLook", True),
                "autoVoiceEnabled": paths.load_settings().get("autoVoiceEnabled", False),
                "awayFromHome": self.network_state.get("awayFromHome", False),
                "homeKnown": self.network_state.get("homeKnown", False),
            },
            "advice": self.evaluated["advice"],
            "handled": self.evaluated["handled"],
            "plans": self.evaluated["plans"],
            "changes": self.changes,
        }

    def state(self):
        state = self.base_state()
        state["resolved"] = self.evaluated["resolved"]
        return state

    def warmed_up(self):
        """True once every background source that can feed the Advisor has produced its
        first real read since Matrix started. Some of these (Tune-up especially) can take
        up to a minute on a cold start -- until then, a suggestion briefly missing from
        advise() just means its source hasn't reported yet, not that the condition is gone
        (see alerts.py's evaluate() for why that distinction matters).

        Network isn't a PeriodicMonitor -- it's built on its own thread (_network_loop)
        with its own first-build delay -- so it's checked separately here rather than
        being covered by the loop below. Same for system: SystemMonitor waits one
        SAMPLE_SECONDS before its very first sample, a much shorter gap than the others
        but a real one, and rules like the driver-check reminder ("Keep as is"-able)
        depend on it having run at least once.

        `self.updates` (UpdateCheckMonitor) is deliberately NOT included below, even
        though it can also feed a persisted, kept/snoozed suggestion. Every check here is
        a local Windows query that's virtually guaranteed to succeed shortly after
        startup; the update check depends on the internet being reachable and GitHub not
        being blocked (a real, ongoing possibility on a school or work network, not just
        a brief startup gap). Gating every other alert's resolution on this one
        succeeding would trade a small, contained risk (the update notice possibly
        re-flagging itself once after a restart) for a much worse one (nothing in the
        whole app can ever resolve on a network where GitHub isn't reachable).
        """
        checks_ready = all(m.checked_at is not None for m in
                            (self.health, self.events, self.tuneup, self.drives, self.thermal)
                            if m.enabled())
        system_ready = (not self.system.available) or bool(self.system.latest)
        network_ready = self.network_at is not None
        return checks_ready and system_ready and network_ready

    # --- the Advisor loop -------------------------------------------------------------

    def _evaluate_loop(self):
        time.sleep(3)  # let the first readings arrive
        while True:
            try:
                self.evaluate()
                self._sample()
                self._snapshot_changes()
            except Exception as err:
                print(f"[matrix] Advisor evaluation failed: {err}")
            time.sleep(EVALUATE_EVERY_SECONDS)

    def _snapshot_changes(self):
        """Once a day (once Tune-up has actually checked), save a settings snapshot and diff it."""
        today = changes.today_str()
        if today == self.last_snapshot_date:
            return
        snap = changes.build_snapshot(self.tuneup.snapshot())
        if snap is None:
            return  # Tune-up hasn't checked yet; try again next tick
        self.last_snapshot_date = today
        result = changes.diff(self.history, snap, today)
        if result and result["sections"]:
            self.changes = result
            titles = ", ".join(s["label"] for s in result["sections"][:3])
            self.history.log("changes", f"What changed since {result['since']}: {titles}",
                             result.get("effect") or "", ref=f"changes:{today}")
        elif result is not None:
            self.changes = None  # nothing changed today; don't keep showing yesterday's diff

    def _digest_loop(self):
        time.sleep(30)  # let the first readings and today's history load
        while True:
            try:
                if digest.due(self.history) and ai.status(options["model"])["installed"]:
                    text = digest.build(options["model"], self.state(), self.history)
                    if text:
                        self.history.save_digest(text)
                        self.history.log("digest", "This week's digest is ready", "", ref=f"digest:{int(time.time())}")
            except Exception as err:
                print(f"[matrix] Weekly digest failed: {err}")
            time.sleep(DIGEST_CHECK_EVERY_SECONDS)

    def evaluate(self):
        with self.eval_lock:
            state = self.base_state()
            events = state["events"]
            self._log_new_crashes(events)
            crash_plan = plans.evaluate(self.history, events) if events.get("checkedAt") else {"state": "unknown"}
            state["plans"] = {"crashes": crash_plan}
            result = self.alerts.evaluate(advisor.advise(state), warmed_up=self.warmed_up())
            self.evaluated = {"advice": result["active"], "handled": result["handled"],
                              "resolved": result["resolved"], "plans": state["plans"]}
            self._update_tray(result["active"])

    def _log_new_crashes(self, events):
        for crash in events.get("crashes") or []:
            ref = f"crash:{crash['time']}"
            if not self.history.logged("crash", ref):
                when = plans._ts(crash["time"])
                self.history.log("crash", crash["title"], crash.get("code") or "", ref=ref, ts=when)

    def _sample(self):
        now = time.time()
        if now - self.last_sample < SAMPLE_EVERY_SECONDS or not self.system.available:
            return
        recent = list(self.system.long_history)[-30:]
        if not recent:
            return
        self.last_sample = now
        avg = lambda values: round(sum(values) / len(values), 1) if values else None
        gpu = [p[3] for p in recent if p[3] is not None]
        temps = [t for t in self.system.gpu_temps if t is not None]
        pc = next((n for n in self.network_state["nodes"] if n["id"] == "this-pc"), None)
        traffic = (pc or {}).get("traffic") or {}
        self.history.add_sample(now, avg([p[1] for p in recent]), avg([p[2] for p in recent]), avg(gpu),
                                max(temps) if temps else None, traffic.get("inKbps"), traffic.get("outKbps"))

    # --- tray and notifications -----------------------------------------------------------

    def _notify(self, title, message):
        print(f"[matrix] Notification: {title}")
        if self.tray:
            self.tray.notify(title, message)

    def _update_tray(self, active):
        if not self.tray:
            return
        critical = [a for a in active if a["urgency"] == "critical"]
        attention = [a for a in active if a["urgency"] == "attention"]
        if critical:
            self.tray.set_status("alert", f"Matrix: {critical[0]['title']}"[:127])
        elif attention:
            self.tray.set_status("warn", f"Matrix: {len(attention)} item{'s' if len(attention) > 1 else ''} to look at")
        else:
            self.tray.set_status("ok", "Matrix: all systems nominal")

    def run_check(self, target):
        """'Check again': re-run one background check, then re-evaluate right away."""
        checks = {"health": self.health, "events": self.events, "tuneup": self.tuneup, "drives": self.drives,
                  "updates": self.updates}
        if target in checks:
            finished = checks[target].run_now_and_wait(timeout=120)
        elif target == "network":
            self.rescan_and_wait()
            finished = True
        elif target in ("system", None, ""):
            time.sleep(2.5)  # one fresh vitals sample
            finished = True
        else:
            raise ValueError("Unknown check.")
        self.evaluate()
        return finished


monitor = Monitor()
options = {"model": ai.DEFAULT_MODEL, "port": 8080}
server_ref = {}


class Server(ThreadingHTTPServer):
    # The dashboard's first load fires off ~30 requests at once (every view's own
    # script file, fonts, the manifest, icons...). socketserver's default backlog
    # (request_queue_size = 5) is fine for one request at a time, but nowhere near
    # enough for that opening burst -- especially on a machine busy with other
    # things, where the server can't call accept() fast enough to keep up. Past
    # that backlog the OS just refuses the extra connections outright
    # (ERR_CONNECTION_REFUSED), silently -- whichever script files land in the
    # overflow are never fetched at all, and since the dashboard's main script
    # imports all of them together, even one missing file means none of it runs.
    # This has to be a class attribute: TCPServer.__init__ calls listen() on
    # construction, so setting this on an instance afterwards is too late.
    request_queue_size = 128


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(paths.APP_DIR), **kwargs)

    def host_ok(self):
        """Only answer requests addressed to this server by name. This blocks "DNS rebinding",
        where another website tricks the browser into sending its requests here."""
        port = self.server.server_address[1]
        return self.headers.get("Host") in {f"localhost:{port}", f"127.0.0.1:{port}"}

    # --- reading ------------------------------------------------------------------

    def do_GET(self):
        if not self.host_ok():
            return self.send_error(403)
        url = urllib.parse.urlparse(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        param = lambda name, default=None: (query.get(name) or [default])[0]
        try:
            if path == "/api/health":
                return self.send_json({"ok": True, "version": paths.VERSION})
            if path == "/api/state":
                return self.send_json(monitor.state())
            if path == "/api/ai":
                return self.send_json(ai.status(options["model"]))
            if path == "/api/settings":
                return self.send_json(settings_payload())
            if path == "/api/history":
                seconds = HISTORY_RANGES.get(param("range", "24h"), 86400)
                return self.send_json(monitor.history.series(seconds))
            if path == "/api/timeline":
                since = param("since")
                limit = min(int(param("limit", "200")), 500)
                return self.send_json({"items": monitor.history.timeline(limit, float(since) if since else None)})
            if path == "/api/device":
                info, hours = monitor.history.device_history(param("mac", ""))
                return self.send_json({"device": info, "presence": presence_summary(hours)})
            if path == "/api/diagnostics":
                monitors = {"Windows health": monitor.health, "Crash and event log": monitor.events, "Tune-up": monitor.tuneup}
                text = diagnostics.report(monitor.state(), monitors, ai.status(options["model"]), monitor.history)
                return self.send_json({"text": text})
            if path == "/api/modes":
                return self.send_json(modes.state())
            if path == "/api/digest":
                latest = monitor.history.latest_digest()
                return self.send_json({"digest": latest, "due": digest.due(monitor.history)})
        except (ValueError, TypeError) as err:
            return self.send_json({"ok": False, "error": str(err)}, 400)
        if path.startswith(("/server/", "/installer/")):  # the dashboard never needs these
            return self.send_error(404)
        return super().do_GET()

    # --- changing things ------------------------------------------------------------

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        routes = {
            "/api/devices": self.handle_devices,
            "/api/identify": self.handle_identify,
            "/api/alerts": self.handle_alerts,
            "/api/plan": self.handle_plan,
            "/api/check": self.handle_check,
            "/api/chat": self.handle_chat,
            "/api/open": self.handle_open,
            "/api/screenshot": self.handle_screenshot,
            "/api/settings": self.handle_settings,
            "/api/modes": self.handle_modes,
            "/api/digest": self.handle_digest,
            "/api/quit": self.handle_quit,
        }
        if path not in routes:
            return self.send_error(404)
        if not self.request_is_from_dashboard():
            return self.send_json({"ok": False, "error": "Requests are only accepted from the Matrix dashboard."}, 403)
        try:
            body = self.read_json_body(limit=100_000 if path == "/api/chat" else 10_000)
            return routes[path](body)
        except (ValueError, TypeError, AttributeError, OSError) as err:
            return self.send_json({"ok": False, "error": str(err)}, 400)

    def handle_devices(self, body):
        action = body.get("action", "save")
        mac = body.get("mac")
        if action == "save":
            network.save_known_device(mac, body.get("name"), body.get("type"))
        elif action == "forget":
            network.forget_known_device(mac)
        elif action in ("ignore", "unignore"):
            network.set_ignored(mac, action == "ignore", body.get("name") or "Ignored device", body.get("type"))
        elif action == "trust-all":
            network.trust_all(monitor.network_state["nodes"])
            monitor.history.log("trusted", "Trusted all current devices", "", ref=f"trust:{int(time.time())}")
        else:
            raise ValueError("Unknown action.")
        monitor.rescan.set()  # show the change on the map right away
        return self.send_json({"ok": True})

    def handle_identify(self, body):
        node = next((n for n in monitor.network_state["nodes"] if n.get("mac") == body.get("mac")), None)
        if not node or not node.get("ip"):
            raise ValueError("That device isn't online right now, so it can't be checked.")
        result = identify.probe_device(node["ip"], node.get("vendor"))
        info, hours = monitor.history.device_history(node["mac"])
        result["presence"] = presence_summary(hours)
        result["firstSeen"] = info["first_seen"] if info else None
        return self.send_json({"ok": True, **result})

    def handle_alerts(self, body):
        monitor.alerts.act(body.get("key"), body.get("action"), body.get("days"))
        monitor.evaluate()
        return self.send_json({"ok": True})

    def handle_plan(self, body):
        plans.mark(monitor.history, body.get("step"), bool(body.get("done", True)))
        monitor.evaluate()
        return self.send_json({"ok": True})

    def handle_check(self, body):
        finished = monitor.run_check(body.get("target"))
        return self.send_json({"ok": True, "finished": finished})

    def handle_open(self, body):
        desktop.open_target(body.get("target"))
        return self.send_json({"ok": True})

    def handle_screenshot(self, body):
        path = diagnostics.screenshot()
        return self.send_json({"ok": True, "path": path})

    def handle_settings(self, body):
        if "autostart" in body or "openWindowAtLogin" in body:
            current = paths.load_settings()
            open_window = bool(body.get("openWindowAtLogin", current["openWindowAtLogin"]))
            paths.save_settings(openWindowAtLogin=open_window)
            enabled = bool(body["autostart"]) if "autostart" in body else desktop.autostart_enabled()
            desktop.set_autostart(enabled, open_window)
        for flag in ("personaEnabled", "autoVoiceEnabled", "livingLook", "awayFromHome"):
            if flag in body:
                paths.save_settings(**{flag: bool(body[flag])})
        if "awayFromHome" in body:
            monitor.rescan.set()  # apply right away instead of waiting for the next scan
        return self.send_json({"ok": True, **settings_payload()})

    def handle_modes(self, body):
        action = body.get("action", "save")
        if action == "save":
            return self.send_json({"ok": True, "modes": modes.save_modes(body.get("modes"))})
        if action == "preview":
            return self.send_json({"ok": True, **modes.preview(body.get("id"))})
        if action == "apply":
            result = modes.apply(body.get("id"))
            monitor.history.log("mode", f"Switched to {result['name']} mode", "; ".join(result["changes"]),
                                ref=f"mode:{int(time.time())}")
            monitor.run_check("tuneup")
            return self.send_json({"ok": True, **result})
        if action == "normal":
            result = modes.revert()
            monitor.history.log("mode", "Back to normal", "; ".join(result["changes"]), ref=f"mode-normal:{int(time.time())}")
            monitor.run_check("tuneup")
            return self.send_json({"ok": True, **result})
        raise ValueError("Unknown action.")

    def handle_digest(self, body):
        if body.get("action") != "generate":
            raise ValueError("Unknown action.")
        text = digest.build(options["model"], monitor.state(), monitor.history)
        if not text:
            raise ValueError("Ollama isn't running, or the model isn't downloaded yet.")
        monitor.history.save_digest(text)
        monitor.history.log("digest", "Weekly digest generated", "", ref=f"digest:{int(time.time())}")
        return self.send_json({"ok": True, "text": text})

    def handle_quit(self, body):
        self.send_json({"ok": True})
        stop_matrix("requested from the dashboard")

    def handle_chat(self, body):
        """Stream the answer as one JSON event per line, as it's generated."""
        messages = ai.validate_messages(body.get("messages"))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()  # no Content-Length: the answer ends when the connection closes
        voice = "argus" if paths.load_settings().get("personaEnabled", True) else None
        try:
            for event in ai.stream_answer(options["model"], messages, monitor.state(), think=body.get("think"), voice=voice):
                self.wfile.write((json.dumps(event) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the user pressed Stop or closed the window; stop generating

    # --- plumbing ------------------------------------------------------------------

    def read_json_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ValueError("Request too large.")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ValueError("Request wasn't valid JSON.")
        if not isinstance(body, dict):
            raise ValueError("Request wasn't a JSON object.")
        return body

    def request_is_from_dashboard(self):
        """Only the Matrix page itself may change things.

        Browsers always say where a request came from (Origin), and a JSON body
        can't be sent cross-site without the browser asking permission first,
        which this server never grants. host_ok() blocks DNS rebinding.
        """
        port = self.server.server_address[1]
        allowed_origins = {f"http://localhost:{port}", f"http://127.0.0.1:{port}"}
        return (
            self.host_ok()
            and self.headers.get("Origin") in allowed_origins
            and self.headers.get("Content-Type", "").startswith("application/json")
        )

    def send_json(self, payload, status=200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Always serve fresh files, so updates show up without a hard refresh.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/" not in self.path:  # keep the log quiet during polling
            super().log_message(fmt, *args)


def settings_payload():
    saved = paths.load_settings()
    return {
        "version": paths.VERSION,
        "autostart": desktop.autostart_enabled(),
        "openWindowAtLogin": saved["openWindowAtLogin"],
        "baselineAt": saved["baselineAt"],
        "dataFolder": str(paths.DATA_DIR),
        "appFolder": str(paths.APP_DIR),
        "model": options["model"],
        "windows": c.IS_WINDOWS,
        "historyMb": monitor.history.size_mb(),
        "personaEnabled": saved["personaEnabled"],
        "autoVoiceEnabled": saved["autoVoiceEnabled"],
        "livingLook": saved["livingLook"],
        "awayFromHome": saved["awayFromHome"],
        "homeKnown": bool(saved["homeGatewayMac"]),
    }


def stop_matrix(reason):
    print(f"[matrix] Stopping ({reason}).")
    if monitor.tray:
        monitor.tray.remove()
    threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()


def send_output_to_log():
    """Without a console (started from the Start menu or at login), write messages to matrix.log."""
    if paths.LOG_FILE.exists() and paths.LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        paths.LOG_FILE.replace(paths.LOG_FILE.with_suffix(".old.log"))
    log = open(paths.LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n[matrix] ---- {datetime.now():%Y-%m-%d %H:%M:%S} Matrix {paths.VERSION} starting ----")


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            return json.load(response).get("ok") is True
    except (OSError, ValueError):
        return False


def start_tray(url):
    """The tray icon (Windows only). Matrix works without it if anything goes wrong."""
    if not c.IS_WINDOWS:
        return
    try:
        import tray

        monitor.tray = tray.TrayIcon(
            paths.APP_DIR / "icons",
            on_open=lambda: desktop.open_window(url),
            on_stop=lambda: stop_matrix("chosen from the tray icon"),
            get_autostart=desktop.autostart_enabled,
            set_autostart=lambda on: desktop.set_autostart(on, paths.load_settings()["openWindowAtLogin"]),
        )
        monitor.tray.start()
    except Exception as err:
        print(f"[matrix] Tray icon unavailable: {err}")
        monitor.tray = None


def make_dpi_aware():
    """Screen coordinates in real pixels, so screenshots capture exactly the Matrix window."""
    if not c.IS_WINDOWS:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    parser = argparse.ArgumentParser(description="Matrix local server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--model", default=ai.DEFAULT_MODEL, help="Ollama model for Ask Matrix")
    parser.add_argument("--open", action="store_true", help="run in the background and open the app window")
    parser.add_argument("--background", action="store_true", help="run in the background without opening a window")
    args = parser.parse_args()
    options["model"], options["port"] = args.model, args.port
    url = f"http://localhost:{args.port}"

    if args.open or args.background or sys.stdout is None:
        send_output_to_log()

    # Only one Matrix at a time: if it's already running, just show its window.
    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError:
        if already_running(args.port):
            print("[matrix] Already running.")
            if args.open:
                desktop.open_window(url)
            return
        print(f"[matrix] Port {args.port} is used by another program. Try --port 8081.")
        sys.exit(1)
    server_ref["server"] = server

    make_dpi_aware()
    imported = paths.migrate_known_devices()
    if imported:
        print(f"[matrix] Imported your device names from {imported}")
    monitor.start()
    start_tray(url)

    print(f"Matrix {paths.VERSION} is running at {url}  (Ctrl+C to stop)")
    print(f"Data folder: {paths.DATA_DIR}")
    if not monitor.system.available:
        print("Tip: live PC vitals need psutil:  python -m pip install psutil")
    ai_status = ai.status(args.model)
    if not ai_status["running"]:
        print("Ask Matrix: Ollama isn't running yet. Start it from the Start menu to use the chat.")
    elif not ai_status["installed"]:
        print(f"Ask Matrix: model not downloaded. Run:  ollama pull {args.model}")
    else:
        print(f"Ask Matrix: ready ({args.model}).")

    if args.open:
        threading.Timer(0.5, desktop.open_window, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    if monitor.tray:
        monitor.tray.remove()
    print("[matrix] Stopped.")


if __name__ == "__main__":
    main()
