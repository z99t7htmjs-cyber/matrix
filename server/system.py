"""
Live vitals for this PC: CPU, memory, disks, GPU, uptime and top programs.

Uses psutil (install with `python -m pip install psutil`). Without it the
dashboard still runs, and the Advisor explains how to turn vitals on.
GPU readings come from `nvidia-smi`, which ships with NVIDIA drivers.
"""

import platform
import shutil
import socket
import threading
import time
from collections import deque

import collectors as c

try:
    import psutil
except ImportError:  # the Advisor tells the user how to install it
    psutil = None

SAMPLE_SECONDS = 2
HISTORY_SAMPLES = 30  # one minute of CPU history for the sparkline and the Advisor
LONG_HISTORY_SAMPLES = 900  # 30 minutes at 2 s, for the Performance charts
LONG_HISTORY_STEP = 5  # send every 5th sample (one point per 10 s) to keep responses small
TOP_PROCESSES = 15
IGNORED_PROCESSES = {"System Idle Process", "Idle", "System", "Registry", "Memory Compression"}


# --- static facts (read once) ----------------------------------------------------

def cpu_name():
    if c.IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except (OSError, ImportError):
            pass
    return platform.processor() or platform.machine()


def windows_version():
    """'Windows 11 Home 24H2 (build 26100)'. The registry still says 'Windows 10' on 11, so use the build number."""
    if not c.IS_WINDOWS:
        return f"{platform.system()} {platform.release()}"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        read = lambda name: winreg.QueryValueEx(key, name)[0]
        build = int(read("CurrentBuildNumber"))
        edition = read("EditionID")
        try:
            release = read("DisplayVersion")
        except OSError:
            release = ""
        product = "Windows 11" if build >= 22000 else "Windows 10"
        return f"{product} {edition} {release} (build {build})".replace("  ", " ")
    except (OSError, ImportError):
        return f"Windows {platform.release()}"


def parse_nvidia_smi(text):
    """Rows from `nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,driver_version --format=csv,noheader,nounits`."""
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6:
            continue
        name, util, used, total, temp, driver = parts
        to_num = lambda v: float(v) if v.replace(".", "", 1).isdigit() else None
        gpus.append({
            "name": name, "usage": to_num(util), "memUsedMb": to_num(used),
            "memTotalMb": to_num(total), "tempC": to_num(temp), "driverVersion": driver or None,
        })
    return gpus


# --- sampler -----------------------------------------------------------------------

class SystemMonitor:
    """Samples vitals in the background so every API request answers instantly."""

    def __init__(self):
        self.available = psutil is not None
        self.static = {"hostname": socket.gethostname(), "os": windows_version(), "cpuName": cpu_name()}
        self.cpu_history = deque(maxlen=HISTORY_SAMPLES)
        self.long_history = deque(maxlen=LONG_HISTORY_SAMPLES)  # (time, cpu, memory, gpu)
        self.gpu_temps = deque(maxlen=60)  # last 2 minutes, for the overheating check
        self.latest = {}
        self.nvidia_smi = shutil.which("nvidia-smi")

    def start(self):
        if not self.available:
            return
        psutil.cpu_percent(interval=None)  # first call primes the counter
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(SAMPLE_SECONDS)
            try:
                self.latest = self._sample()
            except Exception as err:  # keep sampling even if one reading fails
                print(f"[matrix] Vitals sample failed: {err}")

    def _sample(self):
        cpu = psutil.cpu_percent(interval=None)
        self.cpu_history.append(round(cpu, 1))
        memory = psutil.virtual_memory()
        freq = psutil.cpu_freq()

        disks = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            if usage.total < 1e9:  # skip tiny system/recovery volumes
                continue
            disks.append({
                "mount": part.mountpoint, "totalGb": round(usage.total / 1e9, 1),
                "freeGb": round(usage.free / 1e9, 1), "usedPercent": usage.percent,
            })

        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None

        gpus = self._gpus()
        gpu_usage = gpus[0]["usage"] if gpus else None
        self.long_history.append((int(time.time()), round(cpu, 1), memory.percent, gpu_usage))
        self.gpu_temps.append(gpus[0]["tempC"] if gpus else None)
        recent = list(self.long_history)[::-1][::LONG_HISTORY_STEP][::-1]  # newest point always included

        return {
            "history": {
                "t": [p[0] for p in recent], "cpu": [p[1] for p in recent],
                "memory": [p[2] for p in recent], "gpu": [p[3] for p in recent],
            },
            "cpu": {
                "usage": round(cpu, 1), "history": list(self.cpu_history),
                "cores": psutil.cpu_count(logical=True),
                "ghz": round(freq.current / 1000, 2) if freq and freq.current else None,
            },
            "memory": {
                "usage": memory.percent, "usedGb": round(memory.used / 1e9, 1), "totalGb": round(memory.total / 1e9, 1),
            },
            "disks": disks,
            "gpus": gpus,
            "gpuTempHistory": list(self.gpu_temps),
            "uptimeSeconds": int(time.time() - psutil.boot_time()),
            "battery": {"percent": round(battery.percent), "plugged": battery.power_plugged} if battery else None,
            "processes": self._top_processes(),
        }

    def _gpus(self):
        if not self.nvidia_smi:
            return []
        query = "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,driver_version"
        return parse_nvidia_smi(c.run([self.nvidia_smi, query, "--format=csv,noheader,nounits"]))

    def _top_processes(self):
        cores = psutil.cpu_count(logical=True) or 1
        rows = []
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                name = proc.info["name"]
                if not name or name in IGNORED_PROCESSES:
                    continue
                rows.append({
                    "name": name,
                    # Per-process CPU is measured per core; divide so it matches Task Manager.
                    "cpu": round(proc.cpu_percent(interval=None) / cores, 1),
                    "memMb": round(proc.info["memory_info"].rss / 1e6) if proc.info["memory_info"] else 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Browsers run many processes with the same name; combine them like Task Manager does.
        grouped = {}
        for row in rows:
            g = grouped.setdefault(row["name"], {"name": row["name"], "cpu": 0, "memMb": 0, "count": 0})
            g["cpu"] += row["cpu"]
            g["memMb"] += row["memMb"]
            g["count"] += 1
        top = sorted(grouped.values(), key=lambda g: (g["cpu"], g["memMb"]), reverse=True)[:TOP_PROCESSES]
        for g in top:
            g["cpu"] = round(g["cpu"], 1)
        return top

    def snapshot(self):
        return {"available": self.available, **self.static, **self.latest}
