"""
Automatic device identification.

Two clues, both gathered without probing devices aggressively:

  * Manufacturer: the first half of a MAC address (the "OUI") is assigned to
    a manufacturer by the IEEE. The official list is downloaded once, saved
    to the Matrix data folder (oui.csv), and used offline after that.
  * Network name: asked of your router's DNS (reverse lookup), and for
    Windows PCs via NetBIOS (`nbtstat -A`). Lookups run in the background and
    are cached, so the dashboard never waits on them.
"""

import csv
import io
import re
import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import collectors as c

from paths import OUI_FILE
OUI_MAX_AGE_DAYS = 90
NAME_TTL_SECONDS = 600

# Tried in order. Both are the public, official registries of MAC prefixes.
OUI_SOURCES = [
    ("https://standards-oui.ieee.org/oui/oui.csv", "ieee"),
    ("https://www.wireshark.org/download/automated/data/manuf", "wireshark"),
]

# Company-name endings to trim so "Espressif Inc." reads as "Espressif".
_SUFFIXES = re.compile(
    r"(?:[,.]\s*|\s+)(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|gmbh|ag|sa|s\.a|bv|b\.v|plc|pte|oy|ab|srl|technologies|technology|electronics|foundation)\.?$",
    re.IGNORECASE,
)

# Clues that suggest a device type, checked against hostname first, then vendor.
HOSTNAME_HINTS = [
    (("iphone", "android", "galaxy", "pixel", "oneplus", "motorola"), "phone"),
    (("ipad", "tablet", "kindle"), "tablet"),
    (("bravia", "webos", "lgwebos", "smarttv", "samsung-tv", "tizen", "vizio", "hisense", "tcl", "-tv"), "tv"),
    (("appletv", "apple-tv", "roku", "chromecast", "firetv", "fire-tv", "shield"), "media"),
    (("xbox", "playstation", "ps4", "ps5", "nintendo", "switch"), "console"),
    (("sonos", "echo", "homepod", "google-home", "nest-audio", "nest-mini"), "speaker"),
    (("camera", "doorbell", "ring-", "wyze", "arlo", "blink", "reolink"), "camera"),
    (("printer", "epson", "officejet", "laserjet", "deskjet"), "printer"),
    (("nas", "synology", "diskstation", "qnap"), "nas"),
    (("laptop-", "macbook"), "laptop"),
    (("desktop-", "imac", "-pc"), "computer"),
    (("esp-", "esp32", "esp8266", "tasmota", "shelly", "sonoff", "wled", "nest", "ecobee", "hue"), "iot"),
]
VENDOR_HINTS = [
    (("espressif", "tuya", "shelly", "sonoff", "itead", "signify", "philips lighting", "ecobee"), "iot"),
    (("wyze", "ring llc", "arlo", "reolink"), "camera"),
    (("nintendo", "sony interactive"), "console"),
    (("roku",), "media"),
    (("sonos",), "speaker"),
    (("vizio", "hisense", "tcl"), "tv"),
    (("synology", "qnap"), "nas"),
    (("brother", "seiko epson"), "printer"),
]


# --- vendor database -----------------------------------------------------------

def parse_ieee_csv(text):
    """IEEE oui.csv rows: Registry, Assignment (6 hex), Organization Name, Address."""
    table = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 3 and re.fullmatch(r"[0-9A-Fa-f]{6}", row[1]):
            table[row[1].lower()] = row[2].strip()
    return table


def parse_wireshark_manuf(text):
    """Wireshark manuf lines: 'AA:BB:CC<TAB>Short<TAB>Long name'. Only 24-bit prefixes."""
    table = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        prefix = parts[0].strip()
        if len(parts) >= 2 and re.fullmatch(r"[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){2}", prefix):
            name = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else parts[1].strip()
            table[re.sub(r"[:-]", "", prefix).lower()] = name
    return table


def short_vendor(name):
    """'Espressif Inc.' -> 'Espressif', 'ASUSTek COMPUTER INC.' -> 'ASUSTek COMPUTER'"""
    previous = None
    while previous != name:
        previous, name = name, _SUFFIXES.sub("", name).strip(" ,.")
    return name


class VendorDB:
    def __init__(self):
        self.table = {}
        self.status = "loading"  # loading | ready | unavailable

    def start(self):
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        if OUI_FILE.exists() and time.time() - OUI_FILE.stat().st_mtime < OUI_MAX_AGE_DAYS * 86400:
            self.table = self._read_cache()
            if self.table:
                self.status = "ready"
                return
        for url, kind in OUI_SOURCES:
            print(f"[matrix] Downloading manufacturer list (one time): {url}")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Matrix network dashboard)"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    text = response.read().decode("utf-8", errors="replace")
                table = parse_ieee_csv(text) if kind == "ieee" else parse_wireshark_manuf(text)
                if len(table) > 1000:
                    self.table = table
                    self._write_cache(table)
                    self.status = "ready"
                    print(f"[matrix] Manufacturer list saved ({len(table):,} entries).")
                    return
            except Exception as err:  # network errors, HTTP errors, timeouts
                print(f"[matrix] Download failed: {err}")
        # Fall back to an old cache if there is one.
        self.table = self._read_cache()
        self.status = "ready" if self.table else "unavailable"

    def _read_cache(self):
        try:
            with OUI_FILE.open(encoding="utf-8", newline="") as f:
                return {row[0]: row[1] for row in csv.reader(f) if len(row) == 2}
        except OSError:
            return {}

    def _write_cache(self, table):
        with OUI_FILE.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(sorted(table.items()))

    def lookup(self, mac):
        if not mac:
            return None
        if c.is_randomized_mac(mac):
            return "Randomized (private address)"
        name = self.table.get(mac.replace(":", "")[:6])
        if name and name.strip().lower() == "private":
            # The maker paid the IEEE to keep its name off the public list.
            return HIDDEN_MAKER
        return short_vendor(name) if name else None


# --- network names -------------------------------------------------------------

def parse_nbtstat(text):
    """Machine name from `nbtstat -A <ip>`: the first '<00> UNIQUE' entry."""
    match = re.search(r"^\s*(\S+)\s+<00>\s+UNIQUE", text, re.MULTILINE)
    return match.group(1) if match else None


def clean_hostname(name):
    """'Johns-iPhone.lan' -> 'Johns-iPhone'"""
    if not name:
        return None
    name = name.strip().rstrip(".")
    for suffix in (".lan", ".local", ".home", ".localdomain", ".home.arpa", ".router", ".domain"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name or None


class NameResolver:
    """Looks up device names in the background; get() never blocks."""

    def __init__(self):
        self.cache = {}  # ip -> (name or None, looked_up_at)
        self.pending = set()
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=4)

    def get(self, ip):
        with self.lock:
            entry = self.cache.get(ip)
            fresh = entry and time.time() - entry[1] < NAME_TTL_SECONDS
            if not fresh and ip not in self.pending:
                self.pending.add(ip)
                self.pool.submit(self._resolve, ip)
            return entry[0] if entry else None

    def _resolve(self, ip):
        name = None
        try:
            found = socket.gethostbyaddr(ip)[0]
            if found and found != ip:
                name = found
        except (OSError, UnicodeError):
            pass
        if not name and c.IS_WINDOWS:
            name = parse_nbtstat(c.run(["nbtstat", "-A", ip], timeout=8))
        with self.lock:
            self.cache[ip] = (clean_hostname(name), time.time())
            self.pending.discard(ip)


# --- putting it together -------------------------------------------------------

def guess_type(hostname, vendor):
    host = (hostname or "").lower()
    for words, device_type in HOSTNAME_HINTS:
        if any(w in host for w in words):
            return device_type
    vend = (vendor or "").lower()
    for words, device_type in VENDOR_HINTS:
        if any(w in vend for w in words):
            return device_type
    return "unknown"


RANDOMIZED = "Randomized (private address)"
HIDDEN_MAKER = "Unlisted (maker kept private)"
NO_MAKER_CLUE = (RANDOMIZED, HIDDEN_MAKER)


def display_name(hostname, vendor):
    if hostname:
        return hostname
    if vendor == RANDOMIZED:
        return "Private device"
    if vendor and vendor not in NO_MAKER_CLUE:
        return f"{vendor} device"
    return "Unknown device"


# --- "Identify this device" (only when you ask, one device at a time) --------------------

# A handful of single connection attempts, each answering one question.
# Nothing is sent beyond opening and closing the connection.
PROBES = [
    (62078, "iPhone or iPad", "Apple phones and tablets listen here for syncing.", "phone"),
    (7000, "Apple TV, HomePod or Mac (AirPlay)", "AirPlay receivers listen here.", "media"),
    (8009, "Chromecast, Google TV or Nest speaker (Google Cast)", "Google Cast devices listen here.", "media"),
    (8060, "Roku", "Roku players and TVs listen here.", "media"),
    (1400, "Sonos speaker", "Sonos speakers listen here.", "speaker"),
    (9100, "Printer", "Network printers accept print jobs here.", "printer"),
    (554, "Camera (video stream)", "Security cameras and doorbells stream video here.", "camera"),
    (445, "Windows PC or file server", "Windows file sharing listens here.", "computer"),
    (22, "Computer, Raspberry Pi or NAS (SSH)", "Remote login for Linux devices, NAS drives and some routers.", "computer"),
    (80, "Has a web page (router, printer, camera, NAS, smart TV)", "Many devices have a settings page here.", None),
]


def _port_open(ip, port, timeout=0.8):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_device(ip, vendor=None):
    """Light, one-time checks on a single device to help work out what it is."""
    findings = []
    name = None
    try:
        found = socket.gethostbyaddr(ip)[0]
        if found and found != ip:
            name = clean_hostname(found)
    except (OSError, UnicodeError):
        pass
    if name:
        findings.append({"clue": f"Calls itself \"{name}\"", "why": "Its network name, from your router."})
    if c.IS_WINDOWS:
        netbios = parse_nbtstat(c.run(["nbtstat", "-A", ip], timeout=8))
        if netbios:
            findings.append({"clue": f"Windows name \"{netbios}\"", "why": "Windows computers answer with their PC name."})
            name = name or netbios

    with ThreadPoolExecutor(max_workers=len(PROBES)) as pool:
        results = list(pool.map(lambda p: (p, _port_open(ip, p[0])), PROBES))
    guesses = []
    for (port, label, why, dtype), is_open in results:
        if is_open:
            findings.append({"clue": label, "why": f"{why} (port {port} answered)"})
            if dtype:
                guesses.append(dtype)

    if vendor and vendor not in NO_MAKER_CLUE:
        findings.append({"clue": f"Made by {vendor}", "why": "From the first half of its MAC address."})

    guess = guess_type(name, vendor)
    if guess == "unknown" and guesses:
        guess = guesses[0]
    silent = not findings
    return {
        "findings": findings,
        "suggestedName": name,
        "suggestedType": guess,
        "summary": ("It didn't answer any of the checks. Phones (especially Android) usually stay silent like this; "
                    "so do devices with a strict firewall." if silent else None),
    }
