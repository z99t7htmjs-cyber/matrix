# Matrix

A live command center for your own PC and home network. Matrix watches this
computer, Windows and every device it can see on your network. An Advisor
points out anything worth fixing, and a local AI answers questions about it.

Everything runs on your PC. The server only accepts connections from this
computer (127.0.0.1). All checks are read-only: Matrix points you to the right
Windows page instead of changing settings itself.

## Install (and update)

1. Unzip the download anywhere (Downloads is fine).
2. Double-click **Install or Update Matrix**.

The installer copies Matrix to `%LOCALAPPDATA%\Programs\Matrix`, installs the
`psutil` library, adds **Matrix** to the Start menu and desktop, asks whether
to start with Windows, and opens it. You can delete the unzipped folder
afterwards.

**To update:** unzip the new version and double-click **Install or Update
Matrix** again. It stops the running copy, replaces the program and restarts
it. Your data is never touched.

**Your data** (device names, trusted and ignored devices, settings, the log)
lives in `%LOCALAPPDATA%\Matrix`. On first run, Matrix imports device names
saved by older versions from your Downloads folder automatically.

**Uninstall:** Start menu → **Uninstall Matrix**. It asks before deleting
your data.

Needs Python 3 (python.org, with "Add python.exe to PATH" ticked). Ask Matrix
also needs Ollama (below).

## How it runs

Matrix has two parts:

- **A background service** that does the watching. It starts at sign-in if
  you chose that, so it's already running after a crash or restart.
- **The window**, opened from the Start menu or desktop icon. It opens as its
  own app window (Chrome or Edge app mode, no tabs or address bar). Closing it
  leaves the service running; **Settings → Stop Matrix** stops everything.

Opening Matrix while it's already running just brings up the window.

## Views

| View | What's in it |
|---|---|
| **Overview** | The living core (a status cloud with a ring per area, or turn it off for a plain card grid), then "Since your last visit" and one card per area. Click any card -- or ring segment -- to go to its view. |
| **Network** | Map and list of devices. Identify, name, trust or ignore them. |
| **Performance** | Live gauges and charts for 30 minutes, 24 hours, 7 days or 30 days. |
| **Security** | Windows protection with buttons to fix it, exposed services, open connections. |
| **Crashes & events** | Blue screens (stop codes explained), unexpected restarts, repair progress, app crashes with the failing part named, hardware errors. |
| **Tune-up** | Startup apps, preinstalled extras (ranked by real cost), largest programs, settings worth checking, battery vs. plugged-in power settings, battery health, and "What changed" since yesterday. |
| **Modes** | One-click Game / Homework / Battery switches you configure yourself (power plan, Game Mode, apps to close or open). The one place Matrix changes a setting instead of only pointing at it -- every switch previews its changes first, and "Back to normal" undoes the power plan and Game Mode part. |
| **Timeline** | Everything Matrix noticed, newest first: devices joining, crashes, alerts, repairs, mode switches, what changed, weekly digests, AI notes. |
| **Settings** | Auto-start, household devices, data folder, look & voice, stop Matrix. |

The right column is always there: the **Advisor** and **Ask Matrix** (chat).
The **tray icon** by the clock shows status (green, amber, red); click it to open
Matrix, right-click for options. Critical items also appear as Windows notifications.
At the bottom right: **Screenshot** (copies this window, ready to paste) and
**Copy diagnostics** (a troubleshooting report without device names or addresses).

## ARGUS & MOMUS

Matrix's notes -- Advisor cards, the weekly digest, proactive alerts -- are written
in one of two original voices, on by default: **ARGUS**, dry and quietly superior
everywhere day-to-day, and **MOMUS**, who shows up on critical items, rooting
(loudly, in tone only) for things to go wrong while still handing you the fix. Both
are entirely original characters -- no license, no impersonation of anyone else's.

This never changes what Matrix is *allowed to do* -- personas only change the
words. Every fix still goes through the same preview-then-confirm flow as Modes;
nothing is ever applied automatically.

Each Advisor note and the digest can be read aloud with the speaker button, using
your browser's own built-in voice (no cloned or celebrity voice, nothing sent
anywhere). Turn personas or voice off independently in Settings, or turn on
"read critical items aloud automatically."

## Living Look

The whole app runs in a dark navy/cyan/gold look with a flowing, circuit-trace
background instead of boxed panels -- see `design/matrix-living-core.html` for the
reference design if you ever want to push it further.

The Overview can show the living core: a rotating particle sphere for this PC, with
six satellite nodes -- Network, Performance, Security, Crashes, Tune-up, Matrix AI --
each showing a live one-line status and pulsing red when something needs you. Click a
node to jump to its view. It never changes what a number means or where to find it --
the same card grid with the same exact figures sits right below it.

It pauses itself when the window's hidden, the GPU's already busy, or Windows'
"reduce animations" is on, and there's a pause button on the scene itself. Switch back
to the plain card-only "Classic" look any time in Settings -- the background and color
system stay either way, only the animated scene is optional.

## The Advisor

Items come in three levels. **Critical** flashes and notifies you: antivirus or
firewall off, a threat Defender couldn't remove, repeated crashes, a new device
after you trusted your network, sustained overheating, a drive almost out of space.
**Needs attention** is calm. **FYI** is just good to know, and archives itself if
left alone for a week.

What you can do with an item depends on what it is:

- **Check again**: for things Matrix can re-check. Fix it, press the button, and
  it disappears once the check passes. You never mark these done yourself.
- **Got it**: for events (a crash, a removed threat). Quiet until it happens again.
- **Keep as is**: for choices (an app you want to keep). Quiet until the situation changes.
- **Snooze** for a day or a week.

Everything set aside is listed under **Set aside** (with "bring back"), and fixed
items under **Resolved recently**. The Timeline keeps the full history.

**Troubleshooting plans.** Crashes come with ordered steps (repair system files,
repair the Windows image, update drivers, test memory, contact support). Matrix
detects the repair tools and the memory test on its own, or you press "I did this".
Crashes from before your last fix stop counting; if nothing crashes for 3 days, the
plan resolves itself. If it crashes again, you get the next step, never a repeat.

When a new item appears, the local AI writes a short "Matrix says" explanation
on the card (skipped while you're gaming, at most 12 a day).

## What changed, and the weekly digest

Once a day, Matrix compares today's settings (installed and startup apps, running
services, power plan, Game Mode, Storage Sense) with the day before, and shows
what's different in the Tune-up view. When apps were newly installed and memory
use has moved a lot around the same time, it says so ("memory use is up 30% over
the last 3 days, around when X was installed") -- a correlation over the same
window, not proof of a cause.

Once a week (free, the same local model through Ollama), Matrix reads the week's
timeline and changes and writes a short digest with a ranked suggestion, shown on
the Overview. You can also ask it to write one right away.

## Household devices

You don't need to know everyone's MAC address. In the Network view, press
**Trust all current devices**: everything on your network right now is
marked normal, and from then on Matrix only flags devices that join later.
This is called baselining, and it's what professionals do.

For a single device, click it and choose **Name**, **Ignore** (no alerts,
hidden from the map unless "Show ignored" is ticked) or **Forget**.

### Away from home

Matrix's device scan has always been passive -- it only reads the network
information Windows already has (the ARP cache), it never pings or probes
other devices. But once you've used **Trust all current devices**, Matrix
also remembers that network's router, so it recognizes home. On any other
network (school, work, a coffee shop), it automatically stops reading,
listing or flagging other people's devices -- it only keeps watching this
PC. No baseline yet, or want to force it? Flip **Pause device scanning
right now** in Settings. Either way, the Network view, the Overview card,
and the Living Look's network satellite say plainly when this is active.

## Crashes

Windows records every crash in its event logs, and Matrix reads them when it
starts and every 10 minutes. After a blue screen or sudden restart, the
Advisor tells you what happened, what the stop code usually means, and where
to look next (Reliability Monitor, Event Viewer, the crash dump files).
Matrix can't watch a crash as it happens (it goes down with the PC), which is
why starting with Windows matters.

## Ask Matrix (local AI)

1. Install Ollama from <https://ollama.com> (no account needed).
2. Download the model once: `ollama pull qwen3:8b` (about 5 GB).

Every question includes a summary of the live dashboard, so answers are about
your actual PC. Nothing leaves your computer. **Deep think** is slower but
better for hard questions. The AI only writes text; it can't run commands or
change settings, and like any AI it can be wrong.

## What Matrix reads

| Area | Source | How often |
|---|---|---|
| CPU, memory, disks, programs | psutil | every 2 s |
| GPU usage and temperature | `nvidia-smi` | every 2 s |
| Devices on the network | `arp -a`, `route print` | every 5 s |
| This PC's connections and ports | `netstat -ano`, `tasklist` | every 5 s |
| Device names and makers | router DNS, `nbtstat`, IEEE MAC list | cached |
| Defender, firewall, updates, UAC, Remote Desktop | PowerShell | every 5 min |
| Crashes, app crashes, hardware errors | Windows event logs | every 10 min |
| Startup apps, installed apps, running services, settings, power plan | registry and PowerShell | every 30 min |
| Battery vs. plugged-in power settings, battery health report | `powercfg` | every 30 min |
| Defender threat detections | PowerShell | every 5 min |
| Repairs you ran (sfc, DISM, memory test) | Windows logs (CBS.log, dism.log, event log) | every 10 min |
| History (performance, devices, timeline) | Matrix's own database, history.db | every minute |

Limits: Windows only remembers devices it has talked to recently, so sleeping
devices may be missing. Traffic is measured for this PC only. CPU temperature
isn't available from Windows without extra drivers.

## Project structure

```
Install or Update Matrix.bat   double-click to install or update
Uninstall Matrix.bat
installer/                     install.ps1, uninstall.ps1
design/matrix-living-core.html the visual reference for the app's whole look -- match this, not a description of it
index.html, manifest.webmanifest, icons/
css/styles.css
js/app.js                      navigation, live data, page-wide buttons
js/views/                      overview, network, performance, security, events, tuneup, modes, timeline, settings
js/components/                 network map, device details, advisor, chat, shared widgets, living core, living background
js/services/                   polling the server, POST helpers
js/data/, js/utils/            device types, explanations, formatting, layout, voice (Web Speech), persona quips

server/matrix_server.py        web server, background monitors, API, single instance
server/paths.py                data folder, settings, version, importing old names
server/network.py              device map, naming, trusting, ignoring
server/identify.py             manufacturer and name lookup
server/system.py               CPU, memory, disk, GPU, processes, 30-min history
server/windows_health.py       Defender, firewall, updates and more
server/windows_events.py       crashes and stability events
server/tuneup.py               startup apps, preinstalled apps, settings, power settings, battery health
server/changes.py              daily settings snapshot and "what changed?" diff
server/modes.py                one-click Game / Homework / Battery switches
server/advisor.py              rules that turn readings into suggestions
server/ai.py                   Ask Matrix (Ollama)
server/persona.py              ARGUS / MOMUS voice lines and style prompts
server/digest.py               weekly AI digest
server/alerts.py               Advisor item lifecycle (snooze, keep, resolve, archive)
server/plans.py                troubleshooting plans (crash repair steps)
server/repairs.py              detects sfc / DISM runs from Windows' logs
server/history.py              history database and timeline
server/proactive.py            "Matrix says" notes written by the local AI
server/tray.py                 tray icon and notifications
server/diagnostics.py          screenshot and diagnostics report
server/periodic.py             background checks that can re-run on demand
server/desktop.py              app window, auto-start, opening Windows pages
server/collectors.py           arp/route/netstat/tasklist parsing
```

To add an Advisor rule, write a function in `server/advisor.py` that returns
`suggestion(...)` items, add it to `RULES`, and optionally give it a button in
`ACTIONS`.
