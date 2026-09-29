"""
Drive health: is a disk actually dying, not just full.

Read-only, like everything else here. Uses Windows' own Storage Management
API (Get-PhysicalDisk / Get-StorageReliabilityCounter) -- no vendor tool,
no admin prompt beyond what Matrix already runs with. Reliability counters
(wear, temperature, read/write errors) aren't available on every controller
or drive, especially some NVMe drives behind a vendor RAID/passthrough
driver; when they're missing, Matrix still reports the drive's overall
HealthStatus (Healthy/Warning/Unhealthy), which Windows always provides.

A dying drive is one of the most common ways a PC actually fails, and
Windows won't tell you until it's often too late -- free-space checks
(tuneup.py) don't catch this at all, a drive can be nearly empty and still
be failing.
"""

import base64
import json
from datetime import datetime, timezone

import collectors as c
from periodic import PeriodicMonitor

# Wear and health don't meaningfully change minute to minute; checking hourly is plenty
# and keeps this from adding to the background PowerShell load.
CHECK_EVERY_SECONDS = 3600

DRIVE_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$disks = @(Get-PhysicalDisk | ForEach-Object {
  $rel = $_ | Get-StorageReliabilityCounter
  [ordered]@{
    id           = "$($_.DeviceId)"
    model        = "$($_.FriendlyName)".Trim()
    mediaType    = "$($_.MediaType)"
    healthStatus = "$($_.HealthStatus)"
    sizeGb       = [math]::Round($_.Size / 1GB, 1)
    wearPercent  = if ($rel -and $null -ne $rel.Wear) { [int]$rel.Wear } else { $null }
    tempC        = if ($rel -and $null -ne $rel.Temperature) { [int]$rel.Temperature } else { $null }
    readErrors   = if ($rel) { [int64]$rel.ReadErrorsTotal } else { $null }
    writeErrors  = if ($rel) { [int64]$rel.WriteErrorsTotal } else { $null }
  }
})
@{ disks = $disks } | ConvertTo-Json -Depth 5 -Compress
"""


def parse_drives(text):
    """The script prints one JSON object; anything else means the check failed."""
    text = text.strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    disks = data.get("disks")
    if disks is None:
        disks = []
    elif not isinstance(disks, list):
        disks = [disks]  # PowerShell turns a single-item array into a plain value
    return {"disks": disks}


def run_drive_script():
    encoded = base64.b64encode(DRIVE_SCRIPT.encode("utf-16-le")).decode("ascii")
    output = c.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=60)
    return parse_drives(output)


class DriveHealthMonitor(PeriodicMonitor):
    name = "Drive health"
    interval = CHECK_EVERY_SECONDS

    def enabled(self):
        return c.IS_WINDOWS

    def collect(self):
        return run_drive_script()

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at, timezone.utc).isoformat() if self.checked_at else None
        return {"supported": c.IS_WINDOWS, "checkedAt": checked, **(self.latest or {"disks": []})}
