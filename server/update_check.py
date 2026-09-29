"""
Checking GitHub for a newer version of Matrix itself.

Read-only, like everything else here: one plain HTTPS GET to GitHub's public,
unauthenticated API, asking "what's the VERSION string in server/paths.py on
the main branch right now" -- the same kind of outbound request identify.py
already makes to download the network-manufacturer list, nothing new in
kind. No login, no token, nothing about this PC or you sent anywhere; the
request carries no information at all beyond "which file do you want."

This only ever tells the Advisor a newer version exists. Matrix never
downloads or installs anything on its own -- same no-autonomy rule as every
other suggestion here: a recommendation, not an action. Getting the update
still means the same "download, extract, run the installer" steps as today,
until/unless that flow itself gets built out.

Deliberately NOT gated by Monitor.warmed_up() the way the other background
checks are (see matrix_server.py). Those all read from local Windows
queries that are virtually guaranteed to succeed shortly after Matrix
starts. This one depends on the internet being reachable *and* GitHub not
being blocked by a school/work network -- a real, ongoing possibility, not
just a brief startup gap. Gating every other alert's resolution on this one
succeeding would trade a small, contained risk (this one notice possibly
re-flagging itself once after a restart) for a much worse one (nothing in
the whole app can ever resolve on a network where GitHub isn't reachable).
"""

import base64
import json
import re
import urllib.request
from datetime import datetime, timezone

from paths import VERSION
from periodic import PeriodicMonitor

# New versions don't ship more than a few times a week -- checking hourly would just be
# extra background requests for no real benefit, so once every 6 hours is plenty.
CHECK_EVERY_SECONDS = 6 * 3600

REPO = "z99t7htmjs-cyber/matrix"
CONTENTS_URL = f"https://api.github.com/repos/{REPO}/contents/server/paths.py?ref=main"
REPO_URL = f"https://github.com/{REPO}"

_VERSION_RE = re.compile(r'VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"')


def _parse_version(text):
    """'0.11.15' -> (0, 11, 15), for a plain numeric comparison. None if unparseable."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(g) for g in match.groups()) if match else None


def parse_paths_py(raw_json_text):
    """The GitHub contents API returns the file base64-encoded inside a JSON envelope;
    pull the VERSION string back out of it. Returns None if anything about the shape
    is unexpected (missing fields, bad base64, no VERSION line) rather than raising --
    a malformed response should just mean "couldn't check this time", not a crash."""
    try:
        data = json.loads(raw_json_text)
        content = base64.b64decode(data["content"]).decode("utf-8")
    except (json.JSONDecodeError, KeyError, ValueError, UnicodeDecodeError):
        return None
    match = _VERSION_RE.search(content)
    return f"{match.group(1)}.{match.group(2)}.{match.group(3)}" if match else None


def check_for_update(current_version=VERSION):
    """Fetches the latest version string and compares it to what's installed. Returns a
    result dict, or None if the check itself failed (network down, GitHub unreachable,
    unexpected response) -- None means "try again later", not "no update"."""
    request = urllib.request.Request(CONTENTS_URL, headers={
        "User-Agent": "Matrix-dashboard",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        latest = parse_paths_py(response.read().decode("utf-8"))
    if latest is None:
        return None
    latest_t, current_t = _parse_version(latest), _parse_version(current_version)
    return {
        "latestVersion": latest,
        "currentVersion": current_version,
        "updateAvailable": bool(latest_t and current_t and latest_t > current_t),
        "releaseUrl": REPO_URL,
    }


class UpdateCheckMonitor(PeriodicMonitor):
    name = "Update check"
    interval = CHECK_EVERY_SECONDS

    def collect(self):
        return check_for_update()

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at, timezone.utc).isoformat() if self.checked_at else None
        return {"checkedAt": checked, **(self.latest or {"updateAvailable": False})}
