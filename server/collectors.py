"""
Read-only collectors.

Each collector runs one built-in operating-system command and parses its text
output. Nothing here sends traffic to other devices: it only reads what this
computer already knows (its ARP cache, routing table, open sockets and
running programs).

Parsing is kept in small pure functions (parse_*) so each one can be tested
with sample output and read on its own. Windows is fully supported; on macOS
and Linux you get devices and the gateway, but not connections or traffic yet.
"""

import csv
import io
import ipaddress
import platform
import re
import socket
import subprocess
import uuid

IS_WINDOWS = platform.system() == "Windows"

# Well-known ports -> service names, used to label connections.
SERVICES = {
    20: "FTP data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    67: "DHCP", 80: "HTTP", 110: "POP3", 123: "NTP", 135: "Windows RPC",
    137: "NetBIOS", 139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    993: "IMAPS", 995: "POP3S", 1900: "SSDP", 3389: "Remote Desktop",
    5353: "mDNS", 5900: "VNC", 7680: "Windows Update sharing", 8080: "HTTP-alt",
    8443: "HTTPS-alt",
}

MAC_PATTERN = r"[0-9A-Fa-f]{1,2}(?:[:-][0-9A-Fa-f]{1,2}){5}"


# --- helpers -------------------------------------------------------------------

def run(args, timeout=5):
    """Run a command (never through a shell) and return its output, or '' on failure."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            # Stops a console window flashing up on Windows; 0 elsewhere.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def is_ipv4(text):
    try:
        ipaddress.IPv4Address(text)
        return True
    except ValueError:
        return False


def normalize_mac(mac):
    """'4-d9-f5-12-8a-1' or '04:D9:F5:12:8A:01' -> '04:d9:f5:12:8a:01'"""
    return ":".join(part.zfill(2) for part in re.split(r"[:-]", mac.lower()))


def is_randomized_mac(mac):
    """Phones and laptops use 'private' random MACs; those have the locally-administered bit set."""
    return bool(int(mac.split(":")[0], 16) & 0x02)


def is_public(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def split_host_port(address):
    """'192.168.1.20:52344' -> ('192.168.1.20', 52344); '[::]:135' -> ('::', 135)"""
    host, _, port = address.rpartition(":")
    return host.strip("[]"), int(port) if port.isdigit() else 0


# --- this computer -------------------------------------------------------------

def primary_ip():
    """The address this PC uses to reach the internet.

    'Connecting' a UDP socket sends no packets; it only asks the OS which
    interface it would use. 203.0.113.1 is a reserved documentation address.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("203.0.113.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def own_mac():
    """Best guess at this PC's MAC. Returns None if Python had to invent one."""
    node = uuid.getnode()
    if node >> 40 & 0x01:  # multicast bit set = random fallback value
        return None
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


# --- gateway and subnet --------------------------------------------------------

def parse_route_print(text):
    """Rows from Windows `route print -4` Active Routes: destination, netmask, gateway, interface, metric."""
    routes = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 5 and is_ipv4(parts[0]) and is_ipv4(parts[1]) and is_ipv4(parts[3]):
            routes.append({"dest": parts[0], "mask": parts[1], "gateway": parts[2], "iface": parts[3]})
    return routes


def gateway_and_subnet(ip):
    """Return (gateway_ip, ipaddress.IPv4Network) for the interface that owns `ip`."""
    fallback_subnet = ipaddress.ip_network(f"{ip}/24", strict=False)

    if IS_WINDOWS:
        routes = [r for r in parse_route_print(run(["route", "print", "-4"])) if r["iface"] == ip]
        gateway = next((r["gateway"] for r in routes if r["dest"] == "0.0.0.0" and r["mask"] == "0.0.0.0"), None)

        # The local subnet is the most specific "On-link" route (not /32) that contains our IP.
        candidates = []
        for r in routes:
            try:
                net = ipaddress.ip_network(f"{r['dest']}/{r['mask']}", strict=False)
            except ValueError:
                continue
            if ipaddress.ip_address(ip) in net and 0 < net.prefixlen < 32 and not net.is_multicast:
                candidates.append(net)
        subnet = max(candidates, key=lambda n: n.prefixlen, default=fallback_subnet)
        return gateway, subnet

    # macOS / Linux: gateway only; assume a /24, which almost every home network uses.
    match = re.search(r"default via (\S+)", run(["ip", "route", "show", "default"])) or re.search(
        r"gateway:\s*(\S+)", run(["route", "-n", "get", "default"])
    )
    return (match.group(1) if match else None), fallback_subnet


# --- other devices (ARP cache) -------------------------------------------------

def parse_arp(text):
    """IP -> MAC pairs from `arp -a` (Windows, macOS, Linux) or `ip neigh` output."""
    pattern = re.compile(
        r"(\d{1,3}(?:\.\d{1,3}){3})\)?\s+(?:at\s+|dev\s+\S+\s+lladdr\s+)?(" + MAC_PATTERN + r")"
    )
    return [(m.group(1), normalize_mac(m.group(2))) for m in pattern.finditer(text)]


def arp_neighbors(subnet):
    """Devices this PC has recently exchanged traffic with on the local subnet: {ip: mac}."""
    text = run(["arp", "-a"])
    if not text and not IS_WINDOWS:
        text = run(["ip", "neigh"])

    neighbors = {}
    for ip, mac in parse_arp(text):
        addr = ipaddress.ip_address(ip)
        if addr not in subnet or addr in (subnet.network_address, subnet.broadcast_address):
            continue
        first_octet = int(mac.split(":")[0], 16)
        if mac == "ff:ff:ff:ff:ff:ff" or first_octet & 0x01:  # broadcast / multicast
            continue
        neighbors[ip] = mac
    return neighbors


# --- sockets, programs and traffic (Windows) -----------------------------------

def parse_netstat_ano(text):
    """TCP rows from Windows `netstat -ano` -> (established, listening) lists."""
    established, listening = [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 5 or parts[0] != "TCP":
            continue
        _, local, remote, state, pid = parts
        local_ip, local_port = split_host_port(local)
        remote_ip, remote_port = split_host_port(remote)
        row = {
            "local_ip": local_ip, "local_port": local_port,
            "remote_ip": remote_ip, "remote_port": remote_port,
            "pid": int(pid) if pid.isdigit() else None,
        }
        if state == "ESTABLISHED":
            established.append(row)
        elif state == "LISTENING":
            listening.append(row)
    return established, listening


def parse_tasklist(text):
    """PID -> program name from Windows `tasklist /fo csv /nh`."""
    names = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 2 and row[1].isdigit():
            names[int(row[1])] = row[0]
    return names


def parse_netstat_e(text):
    """(bytes_received, bytes_sent) totals from Windows `netstat -e`, or None."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "Bytes" and parts[1].isdigit() and parts[2].isdigit():
            return int(parts[1]), int(parts[2])
    return None


def tcp_sockets():
    if not IS_WINDOWS:
        return [], []
    return parse_netstat_ano(run(["netstat", "-ano"]))


def process_names():
    if not IS_WINDOWS:
        return {}
    return parse_tasklist(run(["tasklist", "/fo", "csv", "/nh"]))


def byte_counters():
    if not IS_WINDOWS:
        return None
    return parse_netstat_e(run(["netstat", "-e"]))
