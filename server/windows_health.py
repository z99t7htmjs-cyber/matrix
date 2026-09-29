"""
Windows security and maintenance health.

One read-only PowerShell script gathers everything and prints JSON. It runs
in the background every few minutes because some of these queries take a
second or two. Nothing here changes any setting.
"""

import base64
import json
from datetime import datetime, timezone

import collectors as c
from periodic import PeriodicMonitor

CHECK_EVERY_SECONDS = 300

HEALTH_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$r = [ordered]@{}

$d = Get-MpComputerStatus
if ($d) {
  # Dropped fields that were collected every 5 min but never read anywhere in the app:
  # AntivirusEnabled (only RealTimeProtectionEnabled is ever checked) and
  # IsTamperProtected (no rule or view ever looked at it).
  $r.defender = [ordered]@{
    realtime         = [bool]$d.RealTimeProtectionEnabled
    signatureAgeDays = [int]$d.AntivirusSignatureAge
    quickScanAgeDays = [int64]$d.QuickScanAge
  }
}

$r.firewall = @(Get-NetFirewallProfile | ForEach-Object {
  [ordered]@{ name = "$($_.Name)"; enabled = ("$($_.Enabled)" -eq 'True') }
})

# Only the date is ever used (for "how long since your last update"); HotFixID was collected
# and never read.
$h = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
if ($h) { $r.lastUpdate = $h.InstalledOn.ToString('yyyy-MM-dd') }

# Get-HotFix only ever shows updates that installed successfully, so "40 days since the
# last one" looks identical whether Windows just hasn't had a new patch to offer, or has
# been silently failing every attempt. The Windows Update Agent's own history (a
# documented, unelevated COM API -- no admin rights needed) tells the two apart: it
# records the actual result of the most recent attempt, success or failure, name intact.
try {
  $session = New-Object -ComObject Microsoft.Update.Session
  $searcher = $session.CreateUpdateSearcher()
  $count = $searcher.GetTotalHistoryCount()
  if ($count -gt 0) {
    $recent = $searcher.QueryHistory(0, [Math]::Min($count, 5)) | Sort-Object Date -Descending | Select-Object -First 1
    if ($recent -and $recent.Date) {
      $r.lastUpdateAttempt = [ordered]@{
        time      = $recent.Date.ToUniversalTime().ToString('o')
        succeeded = ($recent.ResultCode -eq 2 -or $recent.ResultCode -eq 3)  # 2=Succeeded, 3=SucceededWithErrors
        title     = "$($recent.Title)"
      }
    }
  }
} catch {}

$r.rebootPending = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or
                   (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')

# Get-NetConnectionProfile (was $r.networkProfiles) was its own separate query, run every
# 5 minutes, whose result was never read by any advisor rule or any view -- removed entirely
# rather than just trimmed, since it's real work, not just an unused field.

$r.startupApps = @(Get-CimInstance Win32_StartupCommand | ForEach-Object { "$($_.Name)" } | Sort-Object -Unique)

$ts = Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server'
if ($ts) { $r.rdpEnabled = ($ts.fDenyTSConnections -eq 0) }

$uac = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
if ($uac) { $r.uacEnabled = ($uac.EnableLUA -eq 1) }

# Threats Defender detected in the last 30 days (names come from Get-MpThreat)
$names = @{}
Get-MpThreat | ForEach-Object { $names["$($_.ThreatID)"] = @{ name = "$($_.ThreatName)"; severity = [int]$_.SeverityID } }
$r.threats = @(Get-MpThreatDetection | Where-Object { $_.InitialDetectionTime -gt (Get-Date).AddDays(-30) } |
  Sort-Object InitialDetectionTime -Descending | Select-Object -First 10 | ForEach-Object {
    $t = $names["$($_.ThreatID)"]
    [ordered]@{ time = $_.InitialDetectionTime.ToString('o'); id = "$($_.DetectionID)";
                name = if ($t) { $t.name } else { "Threat $($_.ThreatID)" };
                severity = if ($t) { $t.severity } else { 0 };
                removed = [bool]$_.ActionSuccess; files = @($_.Resources | Select-Object -First 3 | ForEach-Object { "$_" }) }
  })

$r | ConvertTo-Json -Depth 5 -Compress
"""


def parse_health(text):
    """The script prints one JSON object; anything else means the check failed."""
    text = text.strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    # PowerShell turns single-item arrays into plain values; normalize them back to lists.
    for key in ("firewall", "startupApps", "threats"):
        value = data.get(key)
        if value is None:
            data[key] = []
        elif not isinstance(value, list):
            data[key] = [value]
    return data


def run_health_script():
    # -EncodedCommand avoids every quoting problem with passing a script on the command line.
    encoded = base64.b64encode(HEALTH_SCRIPT.encode("utf-16-le")).decode("ascii")
    output = c.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=60)
    return parse_health(output)


class HealthMonitor(PeriodicMonitor):
    name = "Windows health"
    interval = CHECK_EVERY_SECONDS

    def enabled(self):
        return c.IS_WINDOWS

    def collect(self):
        return run_health_script()

    def snapshot(self):
        checked = datetime.fromtimestamp(self.checked_at, timezone.utc).isoformat() if self.checked_at else None
        return {"supported": c.IS_WINDOWS, "checkedAt": checked, **(self.latest or {})}
