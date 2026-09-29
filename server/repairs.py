"""
Detects repairs you've run, from Windows' own logs, so Matrix knows what's
already been tried.

  sfc /scannow                    -> C:\\Windows\\Logs\\CBS\\CBS.log  ("[SR]" lines)
  DISM /Online /Cleanup-Image ... -> C:\\Windows\\Logs\\DISM\\dism.log
  Windows Memory Diagnostic       -> System event log (MemoryDiagnostics-Results),
                                     read by windows_events.py

These logs are readable without administrator rights on normal Windows
installs. If one can't be read, Matrix simply falls back to the "I did this"
button for that step.
"""

import os
import re
from datetime import datetime
from pathlib import Path

WINDIR = Path(os.environ.get("WINDIR", r"C:\Windows"))
CBS_LOG = WINDIR / "Logs" / "CBS" / "CBS.log"
DISM_LOG = WINDIR / "Logs" / "DISM" / "dism.log"
TAIL_BYTES = 8_000_000  # these logs grow large; the recent end is all we need

LINE_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _tail(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def _time(line):
    match = LINE_TIME.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def parse_sfc(text):
    """The most recent completed sfc run: when it finished, and whether it found and repaired files."""
    if not text:
        return None
    runs = []
    current = None
    for line in text.splitlines():
        if "[SR]" not in line:
            continue
        ts = _time(line)
        if "Beginning Verify and Repair transaction" in line or "Beginning Verify transaction" in line:
            current = {"started": ts, "finished": None, "repaired": 0, "unrepaired": 0}
            runs.append(current)
        elif current is None:
            continue
        elif "Repairing corrupted file" in line or "Repaired file" in line:
            current["repaired"] += 1
        elif "Cannot repair member file" in line or "could not be repaired" in line.lower():
            current["unrepaired"] += 1
        elif "Verify complete" in line or "Repair complete" in line:
            current["finished"] = ts
    finished = [r for r in runs if r["finished"]]
    if not finished:
        return None
    last = finished[-1]
    if last["unrepaired"]:
        result = "found problems it could not fix"
    elif last["repaired"]:
        result = "found and repaired damaged files"
    else:
        result = "found no problems"
    return {"at": last["finished"], "result": result, "repaired": last["repaired"], "unrepaired": last["unrepaired"]}


def parse_dism(text):
    """The most recent DISM /RestoreHealth run and when it finished."""
    if not text:
        return None
    last = None
    for line in text.splitlines():
        if "Command Line:" in line and "restorehealth" in line.lower():
            last = {"at": _time(line), "result": "ran"}
        elif last and ("successfully" in line.lower() and "restore" in line.lower()):
            last["result"] = "repaired the Windows image"
            last["at"] = _time(line) or last["at"]
    return last if last and last["at"] else None


def detect():
    """What repairs Windows' logs show, keyed by troubleshooting step id."""
    found = {}
    sfc = parse_sfc(_tail(CBS_LOG))
    if sfc:
        found["sfc"] = {"at": sfc["at"], "detail": f"System file check {sfc['result']}"}
    dism = parse_dism(_tail(DISM_LOG))
    if dism:
        found["dism"] = {"at": dism["at"], "detail": f"DISM {dism['result']}"}
    return found
