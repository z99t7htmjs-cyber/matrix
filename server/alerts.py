"""
Alert lifecycle: what happens to each Advisor item over time.

  active        showing in the Advisor
  snoozed       hidden until a date, then back if it still applies
  kept          "Keep as is": hidden until the situation changes (its fingerprint)
  acknowledged  "Got it" for events: hidden until something new happens
  archived      FYI items left alone for a week retire themselves the same way
  resolved      the check passed (twice in a row, so a blip doesn't count)

The Advisor rules (advisor.py) decide WHAT applies right now. This module
remembers what you did about it, so nothing nags you twice and nothing is lost:
every change is written to the timeline.
"""

import threading
import time

import paths
import persona
from advisor import URGENCY_ORDER

STALE_FYI_DAYS = 7  # FYI items nobody acted on archive themselves after this
ABSENT_TO_RESOLVE = 2  # evaluations in a row without the item before it counts as resolved
NOTIFY_AGAIN_AFTER = 6 * 3600
HANDLED = ("snoozed", "kept", "acknowledged", "archived")


class AlertManager:
    def __init__(self, history, notify=None, explain=None):
        self.history = history
        self.notify = notify or (lambda title, message: None)
        self.explain = explain or (lambda item: None)
        self.lock = threading.Lock()
        self.current = {}  # id -> latest suggestion (for actions and output)
        self.transient_state = {}  # snoozes of transient items live only in memory
        self.notified = {}
        self.result = {"active": [], "handled": [], "resolved": []}

    # --- evaluation ------------------------------------------------------------------

    def evaluate(self, suggestions, now=None, warmed_up=True):
        """warmed_up=False means: don't trust an item's absence as "the situation
        resolved" this cycle -- some background check Matrix depends on hasn't
        completed its first read since Matrix started (e.g. Tune-up's checks can take
        up to a minute), so a suggestion missing from `suggestions` right now might
        just mean its check hasn't reported yet, not that the condition went away.
        Without this, every restart -- including every "new edition," since that's
        exactly when Matrix restarts -- could flip a kept/snoozed item to resolved
        within 20 seconds, then re-raise it as brand-new once the slow check finally
        reports, silently discarding "Keep as is" or a snooze for no real reason.
        """
        now = int(now or time.time())
        with self.lock:
            states = self.history.alert_states()
            present = {s["id"]: s for s in suggestions}
            self.current = present

            for item in suggestions:
                if item["transient"]:
                    continue
                self._update_present(item, states.get(item["id"]), now)

            if warmed_up:
                for key, st in states.items():
                    if key in present or st["status"] == "resolved":
                        continue
                    self._update_absent(st, now)

            self.result = self._build(suggestions, now)
            return self.result

    def _save(self, key, status, item, now, raised_at=None, until=None, seen_absent=0, fingerprint=None):
        self.history.save_alert({
            "key": key, "status": status, "fingerprint": fingerprint if fingerprint is not None else item["fingerprint"],
            "title": item["title"], "urgency": item["urgency"], "raised_at": raised_at or now,
            "changed_at": now, "until": until, "seen_absent": seen_absent, "kind": item["kind"],
        })

    def _raise(self, item, now, reason):
        self._save(item["id"], "active", item, now)
        if item["urgency"] != "fyi":
            self.history.log("alert", item["title"], reason, ref=item["id"])
        if item["urgency"] == "critical" or item["id"] == "crashes":
            last = self.notified.get(item["id"], 0)
            if now - last > NOTIFY_AGAIN_AFTER:
                self.notified[item["id"]] = now
                self.notify(item["title"], item["detail"][:200])
        if item["urgency"] != "fyi":
            self.explain(item)

    def _update_present(self, item, st, now):
        key, fp = item["id"], item["fingerprint"]
        if st is None or st["status"] == "resolved":
            self._raise(item, now, "New")
            return
        status = st["status"]
        if status == "snoozed":
            if st["until"] and now >= st["until"]:
                self._raise(item, now, "Snooze ended and it still applies")
            return
        if status in ("kept", "acknowledged", "archived"):
            if st["fingerprint"] != fp:
                self._raise(item, now, "Came back: the situation changed")
            return
        # active: keep details current; retire stale FYI items
        if item["urgency"] == "fyi" and now - (st["raised_at"] or now) > STALE_FYI_DAYS * 86400:
            self._save(key, "archived", item, now, raised_at=st["raised_at"])
            self.history.log("archived", item["title"], "Left alone for a week; archived until something changes.", ref=key)
            return
        if st["fingerprint"] != fp or st["title"] != item["title"] or st["urgency"] != item["urgency"] or st["seen_absent"]:
            self._save(key, "active", item, now, raised_at=st["raised_at"])

    def _update_absent(self, st, now):
        if st["status"] != "active":
            # Handled items whose situation went away are simply finished.
            st = dict(st, status="resolved", changed_at=now)
            self.history.save_alert(st)
            return
        absent = (st["seen_absent"] or 0) + 1
        if absent >= ABSENT_TO_RESOLVE:
            self.history.save_alert(dict(st, status="resolved", changed_at=now, seen_absent=absent))
            # Conditions were fixed; events (a crash, a threat) just aren't current any more.
            if st["urgency"] != "fyi" and st.get("kind") != "event":
                self.history.log("resolved", st["title"], "Fixed: the check now passes.", ref=st["key"])
        else:
            self.history.save_alert(dict(st, seen_absent=absent))

    def _build(self, suggestions, now):
        states = self.history.alert_states()
        persona_on = paths.load_settings().get("personaEnabled", True)
        active, handled = [], []
        for item in suggestions:
            if item["transient"]:
                snooze = self.transient_state.get(item["id"])
                if snooze and now < snooze:
                    handled.append({**item, "status": "snoozed", "until": snooze})
                else:
                    active.append({**item, "status": "active", "raisedAt": now})
                continue
            st = states.get(item["id"])
            if not st:
                continue
            note = self.history.ai_note(f"{item['id']}|{item['fingerprint']}")
            voice, line = (None, None)
            if persona_on:
                snoozes = self.history.count_timeline("snoozed", item["id"])
                age_days = (now - (st["raised_at"] or now)) / 86400
                voice, line = persona.card_voice(item, snoozes=snoozes, age_days=age_days)
            enriched = {**item, "status": st["status"], "raisedAt": st["raised_at"], "until": st["until"],
                        "changedAt": st["changed_at"], "aiNote": note["text"] if note else None,
                        "persona": voice, "personaLine": line}
            (active if st["status"] == "active" else handled).append(enriched)

        active.sort(key=lambda a: (URGENCY_ORDER[a["urgency"]], -(a["raisedAt"] or 0)))
        resolved = sorted((s for s in states.values() if s["status"] == "resolved" and s["urgency"] != "fyi"
                           and s.get("kind") != "event"
                           and now - (s["changed_at"] or 0) < 14 * 86400),
                          key=lambda s: s["changed_at"], reverse=True)[:15]
        resolved_out = []
        for s in resolved:
            voice, line = persona.resolved_voice(s["title"], s["key"]) if persona_on else (None, None)
            resolved_out.append({"id": s["key"], "title": s["title"], "resolvedAt": s["changed_at"],
                                 "persona": voice, "personaLine": line})
        return {
            "active": active,
            "handled": sorted(handled, key=lambda h: h.get("changedAt") or 0, reverse=True),
            "resolved": resolved_out,
        }

    # --- your actions ------------------------------------------------------------------

    def act(self, key, action, days=None):
        now = int(time.time())
        with self.lock:
            item = self.current.get(key)
            if item is None:
                raise ValueError("That item isn't showing any more.")
            if item["transient"]:
                if action == "snooze":
                    self.transient_state[key] = now + int((days or 1) * 86400)
                elif action == "restore":
                    self.transient_state.pop(key, None)
                else:
                    raise ValueError("This one clears itself; you can only snooze it.")
                return
            st = self.history.alert_states().get(key)
            raised = st["raised_at"] if st else now
            if action == "snooze":
                days = min(max(float(days or 1), 0.04), 30)
                self._save(key, "snoozed", item, now, raised_at=raised, until=now + int(days * 86400))
                self.history.log("snoozed", item["title"], f"Snoozed for {days:g} day{'s' if days != 1 else ''}.", ref=key)
            elif action == "keep":
                if item["kind"] != "choice":
                    raise ValueError("This one can't be kept as is.")
                self._save(key, "kept", item, now, raised_at=raised)
                self.history.log("kept", item["title"], "Kept as is. It comes back only if the situation changes.", ref=key)
            elif action == "acknowledge":
                if item["kind"] != "event":
                    raise ValueError("Only events can be acknowledged.")
                self._save(key, "acknowledged", item, now, raised_at=raised)
                self.history.log("acknowledged", item["title"], "Seen. It comes back only if it happens again.", ref=key)
            elif action == "restore":
                self._save(key, "active", item, now, raised_at=raised)
            else:
                raise ValueError("Unknown action.")
            self.result = self._build(list(self.current.values()), now)
