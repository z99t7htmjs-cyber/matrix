"""
Troubleshooting plans: ordered steps for a problem, with memory of what's
already been tried.

Only one plan so far, for crashes (blue screens and unexpected restarts):

  1. Repair Windows system files       (sfc /scannow)           detected from CBS.log
  2. Repair the Windows image          (DISM /RestoreHealth)    detected from dism.log
  3. Update graphics and chipset drivers                        you mark it done
  4. Test the memory                   (Windows Memory Diagnostic) detected from the event log
  5. Contact ASUS support                                       you mark it done

For graphics-related stop codes, driver updates move to the front.

How it decides:
  * A plan starts with the first crash in the last 7 days.
  * A step counts if it was done after the plan started (detected or marked).
  * Only crashes AFTER the latest step count toward the alert. Before that, they
    are history, still shown in Crashes & events but no longer nagging.
  * Step done and no crash since: "watching". After 3 quiet days the plan is
    resolved and closed (it's all kept in the timeline).
  * A crash after a step brings the alert back with the next step, never a repeat.
"""

import time
from datetime import datetime

PLAN = "crashes"
QUIET_DAYS = 3
WINDOW_DAYS = 7
GPU_STOP_CODES = {"0x00000116", "0x00000117", "0x00000119", "0x0000010E"}

STEPS = {
    "sfc": {
        "title": "Repair Windows system files",
        "how": ["Right-click Start → Terminal (Admin).", "Run `sfc /scannow` and wait for it to finish (10–20 minutes).",
                "Restart the PC. Matrix detects the scan by itself."],
        "auto": True,
    },
    "dism": {
        "title": "Repair the Windows image",
        "how": ["Right-click Start → Terminal (Admin).", "Run `DISM /Online /Cleanup-Image /RestoreHealth` (needs internet, 10–30 minutes).",
                "Then run `sfc /scannow` once more and restart. Matrix detects both by itself."],
        "auto": True,
    },
    "drivers": {
        "title": "Update graphics and chipset drivers",
        "how": ["Open the NVIDIA app → Drivers and install the latest Game Ready driver.",
                "Open MyASUS → Customer Support → Live Update and install chipset and BIOS updates.",
                "Restart, then press \"I did this\" on this step."],
        "auto": False,
    },
    "memtest": {
        "title": "Test the memory",
        "how": ["Search the Start menu for \"Windows Memory Diagnostic\".", "Choose \"Restart now and check for problems\".",
                "The result appears after the restart. Matrix reads it by itself."],
        "auto": True,
    },
    "support": {
        "title": "Contact ASUS support",
        "how": ["Crashes after all the steps above point to a hardware fault.",
                "Open MyASUS → Customer Support, or contact ASUS with the crash list from the Crashes & events view.",
                "Press \"I did this\" once you've contacted them."],
        "auto": False,
    },
}
DEFAULT_ORDER = ["sfc", "dism", "drivers", "memtest", "support"]
GPU_ORDER = ["drivers", "sfc", "dism", "memtest", "support"]


def _ts(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def _label(ts):
    return datetime.fromtimestamp(ts).strftime("%b %d, %I:%M %p").replace(" 0", " ")


def evaluate(history, events, now=None):
    """Work out where the crash plan stands. Writes to history (plan start, detected steps, resolution)."""
    now = now or time.time()
    if not events or not events.get("checkedAt"):
        return {"state": "unknown"}

    crashes = [dict(c, ts=_ts(c["time"])) for c in events.get("crashes") or []]
    crashes = [c for c in crashes if c["ts"]]
    recent = [c for c in crashes if now - c["ts"] <= WINDOW_DAYS * 86400]
    started = history.plan_started(PLAN)

    if started is None:
        if not recent:
            return {"state": "none"}
        started = min(c["ts"] for c in recent)
        history.start_plan(PLAN, started)

    # Steps detected from Windows' logs (only if done after the plan started).
    detected = dict(events.get("repairs") or {})
    memdiag = events.get("memdiag")
    if memdiag and _ts(memdiag["time"]):
        detected["memtest"] = {"at": _ts(memdiag["time"]),
                               "detail": "Memory test found no errors" if memdiag["ok"] else "Memory test reported problems"}
    done = history.plan_steps(PLAN)
    for step, info in detected.items():
        if step in STEPS and info["at"] >= started - 60 and step not in done:
            history.mark_step(PLAN, step, info["at"], "detected", info["detail"])
            history.log("repair", f"Detected: {STEPS[step]['title']}", info["detail"], ref=f"{PLAN}:{step}:{int(info['at'])}", ts=info["at"])
    done = history.plan_steps(PLAN)

    fix_at = max((s["done_at"] for s in done.values()), default=None)
    counted = [c for c in recent if fix_at is None or c["ts"] > fix_at + 60]
    counted.sort(key=lambda c: c["ts"], reverse=True)

    latest_code = next((c.get("code") for c in counted or recent if c.get("code")), None)
    order = GPU_ORDER if latest_code in GPU_STOP_CODES else DEFAULT_ORDER
    steps = [{
        "id": sid, "title": STEPS[sid]["title"], "how": STEPS[sid]["how"], "auto": STEPS[sid]["auto"],
        "done": sid in done, "doneAt": done[sid]["done_at"] if sid in done else None,
        "source": done[sid]["source"] if sid in done else None, "detail": done[sid]["detail"] if sid in done else None,
    } for sid in order]
    nxt = next((s for s in steps if not s["done"]), None)

    boot = _ts(events.get("lastBoot") or "")
    fix_step = max(done.values(), key=lambda s: s["done_at"]) if done else None
    base = {
        "steps": steps, "next": nxt, "startedAt": started, "fixAt": fix_at,
        "fixLabel": f"{STEPS[fix_step['step']]['title']} on {_label(fix_at)}" if fix_step else None,
    }

    if counted:
        return {**base, "state": "active", "counted": [{k: v for k, v in c.items() if k != "ts"} for c in counted]}

    if fix_at is None:
        # Crashes aged out of the 7-day window without anything being done: close quietly.
        history.end_plan(PLAN)
        history.log("resolved", "Crashes: none in the last 7 days", "Closed without a repair.", ref=f"{PLAN}:aged:{int(now)}")
        return {"state": "none"}

    quiet = (now - fix_at) / 86400
    if quiet >= QUIET_DAYS:
        history.end_plan(PLAN)
        history.log("resolved", "Crashes resolved", f"No crashes since {base['fixLabel']}.", ref=f"{PLAN}:resolved:{int(now)}")
        return {"state": "none", "resolvedNow": True}

    return {**base, "state": "watching", "quietDays": quiet,
            "restartNeeded": bool(boot and boot < fix_at)}


def mark(history, step, done):
    if step not in STEPS:
        raise ValueError("Unknown step.")
    if history.plan_started(PLAN) is None:
        raise ValueError("There's no crash plan in progress.")
    if done:
        history.mark_step(PLAN, step, time.time(), "you")
        history.log("repair", f"Marked done: {STEPS[step]['title']}", "", ref=f"{PLAN}:{step}:manual:{int(time.time())}")
    else:
        history.unmark_step(PLAN, step)
