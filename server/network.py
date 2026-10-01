"""
Builds the network map: which devices are on your network, what they are,
and anything worth flagging about them.

Output shape (what the web app draws):
  { nodes: [Node], links: [{ source, target }] }
  Node {
    id, name, type, ip, status ("online" | "offline"),
    mac?, vendor?, hostname?,
    known (bool: identity confirmed), saved (bool: listed in known_devices.json),
    ignored (bool: hidden and never alerted on),
    traffic: { inKbps, outKbps } | null     (null = not measurable from this PC)
    connections: [{ protocol, remote, port, service, process? }],
    alerts: [{ id, kind, severity, title, detail, detectedAt }]
  }
"""

import ipaddress
import json
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import collectors as c
import identify

from paths import KNOWN_DEVICES_FILE, load_settings, save_settings, write_json_atomic, now_iso as _now
MAX_CONNECTIONS_SHOWN = 30
RANDOMIZED = "Randomized (private address)"
_file_lock = threading.Lock()  # guards known_devices.json reads and writes


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_known_devices():
    """Read known_devices.json on every build, so edits apply without a restart."""
    try:
        with _file_lock:  # never read while Matrix itself is swapping in a new copy
            text = KNOWN_DEVICES_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
        return {c.normalize_mac(mac): info for mac, info in data.get("devices", {}).items()}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, AttributeError, ValueError) as err:
        print(f"[matrix] Could not read {KNOWN_DEVICES_FILE.name}: {err}")
        return {}


def node_id_for(mac):
    return "mac-" + mac.replace(":", "")


# --- saving names from the dashboard ------------------------------------------------

# Keep in sync with js/data/deviceTypes.js
DEVICE_TYPES = {
    "computer", "laptop", "phone", "tablet", "tv", "media", "console", "speaker",
    "iot", "camera", "printer", "nas", "network", "router", "other", "unknown",
}
MAX_NAME_LENGTH = 40


def clean_name(name):
    """Printable characters only, single spaces, at most 40 characters."""
    name = " ".join(str(name).split())  # tabs, newlines and runs of spaces become one space
    return "".join(ch for ch in name if ch.isprintable())[:MAX_NAME_LENGTH].strip()


def _update_known_file(change):
    """Read the file, apply `change` to its "devices" dict, and write it back safely."""
    with _file_lock:
        try:
            data = json.loads(KNOWN_DEVICES_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("top level is not an object")
        except FileNotFoundError:
            data = {}
        except (json.JSONDecodeError, ValueError) as err:
            # Never overwrite a file we couldn't read: the user might lose their names.
            raise ValueError(f"known_devices.json has a mistake in it ({err}). Fix it or delete it first.")

        devices = {c.normalize_mac(mac): info for mac, info in data.get("devices", {}).items()}
        change(devices)
        data["devices"] = dict(sorted(devices.items()))

        write_json_atomic(KNOWN_DEVICES_FILE, data)


def _check_mac(mac):
    if not re.fullmatch(c.MAC_PATTERN, str(mac)):
        raise ValueError("That isn't a valid MAC address.")
    return c.normalize_mac(mac)


def save_known_device(mac, name, device_type):
    mac = _check_mac(mac)
    name = clean_name(name)
    if not name:
        raise ValueError("Give the device a name.")
    if device_type not in DEVICE_TYPES:
        raise ValueError("Unknown device type.")

    def change(devices):
        previous = devices.get(mac, {})
        devices[mac] = {"name": name, "type": device_type}
        if previous.get("ignored"):
            devices[mac]["ignored"] = True

    _update_known_file(change)


def set_ignored(mac, ignored, name="Ignored device", device_type="unknown"):
    """Ignore (or stop ignoring) a device: no alerts, and hidden from the map by default."""
    mac = _check_mac(mac)
    fallback_type = device_type if device_type in DEVICE_TYPES else "unknown"

    def change(devices):
        entry = devices.setdefault(mac, {"name": clean_name(name) or "Ignored device", "type": fallback_type})
        if ignored:
            entry["ignored"] = True
        else:
            entry.pop("ignored", None)

    _update_known_file(change)


def trust_all(nodes):
    """Save every device currently on the map as known, and remember when (the "baseline").

    From then on, only devices that show up later are flagged as new. This is also how
    Matrix learns what "home" is: it remembers this network's router, so it can recognize
    (and stay quiet on) any other network without being told each time.
    """
    def change(devices):
        for node in nodes:
            mac = node.get("mac")
            if not mac or node["id"] in ("internet", "this-pc") or mac in devices:
                continue
            node_type = node.get("type") if node.get("type") in DEVICE_TYPES else "unknown"
            devices[mac] = {"name": clean_name(node.get("name")) or "Household device", "type": node_type}

    _update_known_file(change)
    router = next((n for n in nodes if n["id"] == "router"), None)
    save_settings(baselineAt=_now(), homeGatewayMac=(router or {}).get("mac"))


def forget_known_device(mac):
    mac = _check_mac(mac)
    _update_known_file(lambda devices: devices.pop(mac, None))


class NetworkBuilder:
    def __init__(self):
        self.vendors = identify.VendorDB()
        self.names = identify.NameResolver()
        self.first_seen = {}  # alert id -> timestamp, so alerts keep their original time
        self.last_bytes = None  # (time, received, sent) for this PC's traffic rate
        self._last_gateway = None  # (ip, mac) from the previous build(), for mid-session spoofing

    def start(self):
        self.vendors.start()

    # --- helpers -----------------------------------------------------------------

    def alert(self, node_id, kind, severity, title, detail):
        alert_id = f"{node_id}-{kind}"
        self.first_seen.setdefault(alert_id, now_iso())
        return {"id": alert_id, "kind": kind, "severity": severity, "title": title,
                "detail": detail, "detectedAt": self.first_seen[alert_id]}

    def measure_traffic(self):
        counters = c.byte_counters()
        if counters is None:
            return None
        now = time.time()
        previous, self.last_bytes = self.last_bytes, (now, *counters)
        if previous is None:
            return {"inKbps": 0, "outKbps": 0}
        elapsed = max(now - previous[0], 0.001)
        return {
            "inKbps": max(0, round((counters[0] - previous[1]) * 8 / 1000 / elapsed)),
            "outKbps": max(0, round((counters[1] - previous[2]) * 8 / 1000 / elapsed)),
        }

    def listening_alerts(self, listening):
        exposed = sorted({row["local_port"] for row in listening if row["local_ip"] not in ("127.0.0.1", "::1")})
        alerts = []
        if 445 in exposed:
            alerts.append(self.alert("this-pc", "smb-exposed", "low", "SMB file sharing listening",
                                     "Port 445 accepts connections from other devices on the network."))
        if 3389 in exposed:
            alerts.append(self.alert("this-pc", "rdp-exposed", "medium", "Remote Desktop is enabled",
                                     "Port 3389 accepts Remote Desktop connections from the network."))
        if exposed:
            shown = ", ".join(str(p) for p in exposed[:12]) + (" …" if len(exposed) > 12 else "")
            alerts.append(self.alert("this-pc", "listening-ports", "info",
                                     f"{len(exposed)} ports open to the network", f"Listening on: {shown}"))
        return alerts

    # Well-known public resolvers, for the DNS sanity check below -- not exhaustive, just
    # the handful a reasonable person might actually have configured on purpose.
    KNOWN_PUBLIC_DNS = {
        "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112",
        "208.67.222.222", "208.67.220.220",
    }

    def unsecure_network_alerts(self, gateway, router_mac, subnet, away, home_known):
        """0.12: real, checkable things worth a note on an unfamiliar network. Attached
        to this-pc since that's where the existing "Exposed to your network" card
        already reads its alerts from -- no new UI needed."""
        alerts = []
        auth = c.wifi_security()
        if auth and auth.lower() == "open":
            alerts.append(self.alert("this-pc", "open-wifi", "medium", "This Wi-Fi network has no password",
                                     "Anyone nearby can see traffic on this network. Avoid signing into anything "
                                     "sensitive here, or use a VPN -- Matrix can't see inside your browser traffic "
                                     "to protect that part for you."))
        if gateway and router_mac:
            previous = self._last_gateway
            if previous and previous[0] == gateway and previous[1] != router_mac:
                alerts.append(self.alert("this-pc", "gateway-changed", "high",
                                         "This network's router changed mid-session",
                                         f"Same address ({gateway}) answered from a different device just now. "
                                         "That can be an ordinary router reboot, or a sign someone's spoofing "
                                         "this network -- worth a second look if anything else seems off."))
            self._last_gateway = (gateway, router_mac)
        dns = c.dns_servers()
        odd_dns = [ip for ip in dns if ip not in self.KNOWN_PUBLIC_DNS and
                  not (subnet and ipaddress.ip_address(ip) in subnet)]
        if away and odd_dns:
            alerts.append(self.alert("this-pc", "unusual-dns", "low", "This network's DNS looks unfamiliar",
                                     f"Handed out {', '.join(odd_dns)} -- not your router and not a well-known "
                                     "public resolver. Often harmless, but public Wi-Fi occasionally redirects DNS "
                                     "to inject ads or worse."))
        if away and home_known:
            alerts.append(self.alert("this-pc", "unfamiliar-network", "info", "You're on a different network than usual",
                                     "Matrix is going easier on device scanning here, same as always on a network "
                                     "that isn't home -- worth knowing while you're out."))
        return alerts

    def describe_device(self, ip, mac, known):
        """Combine known_devices.json, manufacturer and network name into one identity."""
        info = known.get(mac) or {}
        vendor = self.vendors.lookup(mac)
        hostname = self.names.get(ip) if ip else None
        return {
            "name": info.get("name") or identify.display_name(hostname, vendor),
            "type": info.get("type") or identify.guess_type(hostname, vendor),
            "vendor": vendor, "hostname": hostname, "known": bool(info),
            "ignored": bool(info.get("ignored")),
        }

    def identity_alerts(self, node_id, mac, ident, baseline_at):
        """Flag devices you haven't named or trusted yet."""
        if ident["known"] or ident.get("ignored"):
            return []
        clues = []
        if ident["hostname"]:
            clues.append(f"calls itself \"{ident['hostname']}\"")
        if ident["vendor"] and ident["vendor"] not in identify.NO_MAKER_CLUE:
            clues.append(f"is made by {ident['vendor']}")
        described = f"This device {' and '.join(clues)}." if clues else f"No name or manufacturer found for {mac}."

        if baseline_at:
            # After "Trust all current devices", anything unknown arrived since then.
            return [self.alert(node_id, "new-device", "medium", "New device on your network",
                               f"{described} It wasn't here when you trusted your devices on "
                               f"{baseline_at[:10]}. Name it, trust it or ignore it if it's expected.")]
        if clues:
            return [self.alert(node_id, "unconfirmed-device", "info", "Identified, not yet confirmed",
                               f"{described} If that's right, confirm it with \"Name this device\" above.")]
        extra = {
            RANDOMIZED: " It uses a private (randomized) MAC, which phones, tablets and laptops do.",
            identify.HIDDEN_MAKER: " Its maker keeps its name off the public list, so the MAC gives no clue.",
        }.get(ident["vendor"], "")
        return [self.alert(node_id, "new-device", "medium", "Unrecognized device",
                           f"{described}{extra} If you recognize it, name it with \"Name this device\" above.")]

    # --- build ---------------------------------------------------------------------

    def build(self):
        known = load_known_devices()
        settings = load_settings()
        baseline_at = settings.get("baselineAt")
        my_ip = c.primary_ip()

        internet = {"id": "internet", "name": "Internet", "type": "internet", "ip": None, "status": "offline",
                    "known": True, "traffic": None, "connections": [], "alerts": []}
        if not my_ip:
            internet["alerts"].append(self.alert("internet", "no-network", "high", "No network connection",
                                                 "This PC has no route to the internet."))
            return {"nodes": [internet], "links": []}

        gateway, subnet = c.gateway_and_subnet(my_ip)
        neighbors = c.arp_neighbors(subnet)
        established, listening = c.tcp_sockets()
        programs = c.process_names()

        if any(c.is_public(row["remote_ip"]) for row in established):
            internet["status"] = "online"
        nodes, links = [internet], []

        # Router (the default gateway)
        router_mac = neighbors.pop(gateway, None) if gateway else None
        router_ident = self.describe_device(gateway, router_mac, known) if router_mac else {}
        nodes.append({
            "id": "router", "name": (known.get(router_mac) or {}).get("name", "Router"), "type": "router",
            "ip": gateway, "mac": router_mac, "vendor": router_ident.get("vendor"),
            "hostname": router_ident.get("hostname"), "known": True, "saved": router_mac in known,
            "status": "online" if gateway else "offline", "traffic": None, "connections": [], "alerts": [],
        })
        links.append({"source": "internet", "target": "router"})

        # Away from home: a manual pause, or this router's MAC doesn't match the one
        # "Trust all current devices" remembered as home. Either way, don't scan or
        # fingerprint whoever else is on this network -- just watch this PC.
        home_mac = settings.get("homeGatewayMac")
        away = bool(settings.get("awayFromHome")) or bool(home_mac and router_mac and home_mac != router_mac)

        # This PC
        my_mac = c.own_mac()
        connections = []
        for row in established:
            if row["remote_ip"] in ("127.0.0.1", "::1"):
                continue
            connections.append({
                "protocol": "TCP", "remote": row["remote_ip"], "port": row["remote_port"],
                "service": c.SERVICES.get(row["remote_port"], "Unknown"), "process": programs.get(row["pid"]),
            })
        connections.sort(key=lambda x: (not c.is_public(x["remote"]), x["process"] or "", x["remote"]))
        my_info = known.get(my_mac) or {}
        pc_alerts = (self.listening_alerts(listening) +
                     self.unsecure_network_alerts(gateway, router_mac, subnet, away, bool(home_mac)))
        nodes.append({
            "id": "this-pc", "name": my_info.get("name", f"This PC ({socket.gethostname()})"),
            "type": my_info.get("type", "computer"), "ip": my_ip, "mac": my_mac,
            "vendor": self.vendors.lookup(my_mac), "hostname": socket.gethostname(), "known": True,
            "saved": my_mac in known,
            "status": "online", "traffic": self.measure_traffic(),
            "connections": connections[:MAX_CONNECTIONS_SHOWN], "alerts": pc_alerts,
            "wifiAuth": c.wifi_security(), "dns": c.dns_servers(),
        })
        links.append({"source": "router", "target": "this-pc"})

        if not away:
            # Everything else this PC has seen recently
            seen = {my_mac, router_mac}
            for ip, mac in sorted(neighbors.items(), key=lambda kv: ipaddress.ip_address(kv[0])):
                if mac in seen:
                    continue
                seen.add(mac)
                node_id = node_id_for(mac)
                ident = self.describe_device(ip, mac, known)
                nodes.append({
                    "id": node_id, "ip": ip, "mac": mac, "status": "online", "traffic": None, "connections": [],
                    **ident, "saved": ident["known"], "alerts": self.identity_alerts(node_id, mac, ident, baseline_at),
                })
                links.append({"source": "router", "target": node_id})

            # Known devices that aren't in the ARP cache right now
            for mac, info in known.items():
                if mac in seen:
                    continue
                node_id = node_id_for(mac)
                nodes.append({
                    "id": node_id, "name": info.get("name", "Known device"), "type": info.get("type", "unknown"),
                    "ip": None, "mac": mac, "vendor": self.vendors.lookup(mac), "known": True, "saved": True,
                    "ignored": bool(info.get("ignored")), "status": "offline",
                    "traffic": None, "connections": [], "alerts": [],
                })
                links.append({"source": "router", "target": node_id})

        # Drop empty optional fields so the web app only shows what we actually know.
        for node in nodes:
            for key in ("mac", "vendor", "hostname"):
                if key in node and not node[key]:
                    del node[key]
        return {"nodes": nodes, "links": links, "awayFromHome": away, "homeKnown": bool(home_mac)}
