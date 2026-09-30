# Matrix roadmap

## How changes are shipped

- Bugs and small requests are collected here and shipped together in the next
  batch, unless Rob asks for something to be fixed right away.
- Each batch is installed by running "Install or Update Matrix" once.

## Next batch (0.12)

Bugs and requests found while using 0.11 go here. Planned in detail on
Sep 30 (talked through tradeoffs live with Rob rather than guessing at
scope); nothing below is built yet -- this is the plan, not a changelog.

**Power: plugged-in vs on-battery, switched automatically**
- [ ] New Settings toggle, off by default: "Auto-switch power mode when I
      plug in or unplug." Only when Rob turns this on does Matrix ever
      change something without a click in the moment -- first time
      anything in Matrix works that way, so it's opt-in and every switch
      still tells him plainly ("Plugged in -> Desktop mode applied").
- [ ] **Desktop mode** (plugged in): High performance power plan, max
      processor state, nothing throttled, nothing closed -- the actual
      goal is "20 Chrome tabs and 5 AI apps fighting each other with zero
      slowdown," which is a power-plan/processor-state question more than
      an app-closing one.
- [ ] **Locked-down mode** (on battery): a more conservative power plan
      (Power saver vs. Balanced -- still need Rob's call on which; Power
      saver may be too aggressive for actually getting schoolwork done).
  - **Apps to close on battery, decided:** the RGB/lighting stack only --
    on battery he's away from the Govee lights and the SteelSeries Arena
    7 speakers entirely, so anything driving them is dead weight. Primary
    suspect is **SignalRGB** (he believes it's already the thing driving
    both Govee and the Arena 7's lighting, so closing it should cover
    both without needing separate Govee/SteelSeries entries). **Confirmed
    from Rob's Task Manager, three separate processes, all three go in
    `closeApps`:** `SignalRgb.exe`, `SignalRgbLauncher.exe`,
    `SignalRgbService.exe` -- closing only the main exe risks the
    Launcher or Service relaunching it, so all three close together.
    Not verified live: whether the Service still tries to resurrect
    things anyway after this ships -- if so, quick follow-up fix, not a
    redesign. Also close whatever's running an animated wallpaper, if
    anything -- his reasoning (animated > static for battery drain) is
    correct.
  - **Explicitly NOT closed on battery:** Chrome, ChatGPT, Claude, PuTTY,
    or anything to do with his Bluetooth mouse -- those are exactly what
    he's actively using at school; Locked-down tightens the power plan
    around them, it doesn't take them away.
- [ ] Small, quiet status dot near the top of the app showing which side
      you're on -- NOT red (red already means "something's actually
      wrong" everywhere else in Matrix; using it for "you're on battery"
      would cry wolf). Cool blue-ish glow for Desktop, warm amber for
      Locked-down, plus a one-word label. Its own on/off switch in
      Settings so it can be hidden if it ever feels like noise.

**Wake-source log (the mouse-waking-the-house problem)**
- [ ] Rob's laptop keeps waking from sleep on tiny mouse movement --
      Govee lights, SteelSeries Arena 7 lights, and a bright screen all
      kick on in a dark bedroom at night. Already ruled out the easy
      fixes (Device Manager's "allow this device to wake," checked wake
      logs by hand) -- still happens. Only real fix last night: unplug
      the mouse.
  - Likely real causes, not yet confirmed on his actual machine: a
    wireless mouse dongle usually shows up as *multiple* wake-armed
    devices (receiver, HID entry, sometimes the USB hub too) -- disabling
    only the one obviously named "mouse" can leave another one armed.
    `powercfg /devicequery wake_armed` shows the complete live list. Also
    worth checking `powercfg /a` (this laptop almost certainly uses
    Modern Standby, which handles wake differently than classic sleep),
    and the ASUS BIOS's own USB-wake/ErP setting, which can override
    whatever Windows is told.
  - **This batch:** just add a plain background log (`powercfg /lastwake`
    read shortly after each wake, kept as a simple persisted history) --
    nothing flashy, no UI polish, just data. The BIOS step-by-step
    walkthrough is a separate live conversation for later, once the log
    has real data to point at instead of guessing.

**Security page: real coverage, not just the Windows-protection checklist**
- [ ] Who has admin rights on this PC (local accounts with admin access).
- [ ] Startup persistence check -- a security-framed pass over
      startup/registry entries (separate from Tune-up's "these slow your
      boot" view), looking for anything that looks snuck-in rather than
      installed on purpose.
- [ ] What this PC is sharing on the network (actual file/folder shares,
      not just listening ports -- "Exposed to your network" doesn't cover
      this today).
- [ ] Hosts file check (a classic malware tampering target -- quietly
      redirects where a site actually goes).
- [ ] Network profile awareness (Public vs Private/Home) -- the
      `Get-NetConnectionProfile` call removed in 0.11.12 for being
      unread now has a real purpose: flag being on "Public" while
      actually on trusted home Wi-Fi, or vice versa.
- [ ] Not added: drive-encryption status -- Rob already confirmed Device
      Encryption is on (free, built into Home, no Pro upgrade needed), so
      this isn't a gap.

**Unsecure/public Wi-Fi detection** (school, coffee shops, anywhere not home)
- [ ] Open/unsecured network warning -- flagged clearly, different tone
      than a routine FYI.
- [ ] "Unfamiliar network" heightened alertness -- when Matrix sees a
      network that isn't the saved home one, turn up how prominently it
      surfaces device/connection alerts.
- [ ] Gateway/router MAC-address change mid-session -- a textbook sign of
      spoofing if it happens without an actual network switch.
- [ ] DNS server sanity check -- public Wi-Fi sometimes hands out sketchy
      DNS to inject ads or worse.
  - Told Rob plainly what this can't do: it can't see inside browser
    traffic (nor should it), so it can't promise "this connection isn't
    being intercepted" -- that's what a VPN is for, a separate tool, not
    something Matrix should pretend to reinvent.

**Efficiency-report leftovers, finally closed out**
- [ ] Backup status (is File History / a backup drive / OneDrive actually
      running, when did it last succeed).
- [ ] BIOS version display (informational only, same spirit as driver
      version -- "what's installed," not "is something newer available"
      yet).
- [ ] Disk cleanup: preview-the-list-then-confirm, not silent
      auto-delete -- same click-to-apply pattern as every other fix in
      Matrix.
  - CPU temperature monitoring: explicitly NOT doing this. Reading it
    reliably means giving Matrix (or a helper) admin rights it doesn't
    otherwise need -- a real architecture tradeoff Rob decided isn't
    worth crossing. Don't revisit without him raising it again.

**ARGUS & MOMUS: more proactive, and actually distinct**
- [ ] Right now the personas mostly only speak up on new Advisor items.
      Rob wants them treated as always-on commentary using *anything*
      Matrix already monitors as material -- not just fresh alerts, but
      chronic-but-minor conditions (memory's been high for days, Chrome
      tab hoarding that never gets addressed) and even neutral/good-news
      moments, so the app isn't only ever heard from when something's
      wrong.
  - **Rob's direct feedback, unprompted:** "so far I am not seeing any
    attitudes" -- the two personas don't currently read as distinct to
    him in actual use. Before or alongside making them chattier, look at
    why: read through the current quip bank and how often it actually
    fires, and fix the root cause rather than just adding more volume to
    a voice that isn't landing.
  - Explicitly NOT adding weather or any other external data source for
    this -- Rob confirmed the material should come from what Matrix
    already monitors on the PC, not a new outbound connection. (Matrix
    has exactly one external connection today, the GitHub version check,
    added only after talking it through the same way.)

- Carried over from 0.10: Do Not Disturb for Modes has no reliable public API on
  current Windows, so it was left out; Armoury Crate's Silent / Performance / Turbo
  still can't be switched from Matrix (ASUS has no public interface). Revisit if
  a way turns up.
- Driver tracking currently surfaces the *installed* version only (monthly FYI
  nudge pointing at the NVIDIA app / MyASUS). True "compare against latest
  available" would mean Matrix reaching out to NVIDIA itself on a schedule --
  left out for now rather than build it against an undocumented endpoint.
- Ring-segment clicks on the living core jump to the closest matching view
  (e.g. "Maintenance" → Tune-up) rather than truly filtering that view to just
  that area's events -- no view currently supports area filtering, and adding
  it everywhere was out of scope for this batch.

## Shipped in 0.11.0: ARGUS & MOMUS, driver visibility, and the Living Look

Two named personas for Matrix's AI voice (original characters, not licensed ones):
- **ARGUS** -- the default everywhere. Dry, quietly superior, keeps score of advice
  you ignored. Replaces the plain "Matrix says" notes, the weekly digest, and
  proactive alerts.
- **MOMUS** -- rooting for your downfall in tone only; still complies with every fix,
  chagrined about it. Shows up on critical items so it stays a treat, not wallpaper.

Rules (all held):
- [x] No-autonomy rule holds for both: persona changes *language only*, never what the
      AI is allowed to do. Every fix still goes through the existing preview → confirm
      pattern (like Modes), never auto-applied.
- [x] Quip bank tied to real triggers: repeated snoozes, a suggestion still active a
      while later, a check that still needs attention vs. one that resolved, a critical
      item resolving itself. Seeded deterministically per item so the line doesn't
      flicker between polls. Critical/factual alert text itself stays flat and direct --
      only the persona line riding alongside it carries the personality.
- [x] Optional read-aloud (TTS) for Advisor notes and the digest, via the browser's own
      Web Speech API -- no cloned or celebrity voice, no server-side voice work at all.
      Auto-read-critical-aloud is a separate, off-by-default setting.
- [x] Settings toggle: personas on/off (falls back to plain text) and voice on/off,
      independently, plus auto-voice-on-critical as its own switch.

Louder, more proactive AI (same no-autonomy ceiling: ranked recommendation +
one-click apply, never automatic):
- [x] Driver visibility: installed NVIDIA driver version now shown and tracked, with a
      monthly Advisor FYI nudging you to check the NVIDIA app / MyASUS Live Update
      (see the scope note above -- no "latest available" comparison yet).
- [ ] More proactive settings tweaks, not just reactive to a problem already present --
      not done this batch, revisit later.
- [ ] Push toward "nothing sits as static text with no action" wherever an action
      genuinely exists -- ongoing, not a one-batch project.

## Shipped in 0.11.16: single-file installer, and a Security-page layout fix

- [x] **Single-file installer** (`Matrix Setup.bat`). Instead of a zip you
      unpack and then run a script inside, this is one file: double-click it
      and it unpacks itself into a temp folder, runs the same
      `installer\install.ps1` as always, then deletes the temp folder. Built
      by hand (no 7-Zip or similar available in this sandbox) as a small
      PowerShell header plus the zipped app appended as base64 text after a
      marker line. Verified in this sandbox: the exact extraction logic
      (find the marker, join everything after it, base64-decode) reproduces
      the original zip byte-for-byte, and the decoded zip's contents are
      intact (all 83 files). **Not** verified: the real double-click-and-run
      on an actual Windows machine, since this sandbox has none -- that
      first real run on Rob's laptop is the true test. The old zip +
      separate install.ps1 flow still works exactly as before; this is an
      addition, not a replacement.
- [x] **Security page: "Open" buttons were stretched to the far edge of the
      card.** The checklist row's middle column used `1fr`, so on a wide
      card it grabbed all the leftover space and shoved the button away from
      its label/value -- cosmetic only, nothing was broken. Capped that
      row's width (`.health--buttons .health-row { max-width: 460px }`) so
      the button sits right after the text. Verified with a headless-browser
      screenshot against mock health data before/after the change.

## Shipped in 0.11.15: Matrix now lives on GitHub, and can tell you when it's out of date

Rob asked to streamline how each new edition gets installed. That split into
two separate things: where new versions live, and how automatic getting
them should be. Talked through both with Rob before building -- landed on
a public GitHub repo (github.com/z99t7htmjs-cyber/matrix) plus a
notify-only update check, deliberately not a self-installing one, matching
the same "recommend, don't auto-act" spirit as everything else in Matrix.

- [x] **The code now lives at github.com/z99t7htmjs-cyber/matrix.** Public
      repo -- Rob's own data, network, and anything Matrix finds on his PC
      is never in it, same as always; only the app's own source is. Pushed
      as one clean initial commit (this repo's own history starts here,
      not a re-creation of every internal iteration).
  - Two real platform limits hit and worked around honestly rather than
    silently: creating a GitHub *Release* (the labeled-snapshot-with-
    download-link feature) is blocked for this session type, and so is
    pushing a plain git *tag* -- both return a clean 403 rather than
    working. Redesigned the update-check around neither: it just asks
    "what does `server/paths.py`'s VERSION string say on the main branch
    right now," via GitHub's public, read-only contents API. No release,
    no tag, no login needed -- verified this actually works fully
    unauthenticated against the live repo before writing a line of the
    monitor code.
- [x] **Matrix checks for updates itself now** (`server/update_check.py`,
      new `UpdateCheckMonitor`, checked every 6 hours). When the version on
      GitHub is newer, it's a normal Advisor card ("Matrix 0.11.16 is
      available"), same as any other suggestion -- not a popup, not
      anything automatic. Matrix still never downloads or installs
      anything on its own; the card's steps are the same "open the link,
      extract, run the installer" flow as always. **Deliberately not
      gated by `Monitor.warmed_up()`** the way every other background
      check now is (see 0.11.13/0.11.14 above) -- this one depends on the
      internet being reachable and GitHub not being blocked, which can
      genuinely never resolve on a locked-down network, and blocking every
      other alert's resolution on that would be a worse bug than the one
      it would prevent. Documented the reasoning directly in
      `Monitor.warmed_up()`'s own docstring so this doesn't get
      "helpfully" added to the gate by a future session without re-reading
      why it was left out.

Not done, still ahead: a real one-click "apply this update" button (Matrix
running the installer itself instead of Rob re-downloading by hand) --
Rob was told plainly this is a bigger, separate piece of work and it hasn't
been started.

Verified: `update_check.py`'s version parsing and comparison logic
unit-tested directly, including against the real, live API response from
the actual repo (fetched once, saved, and replayed) -- not a synthetic
fixture. The end-to-end monitor lifecycle (before-check state ->
collect() -> after-check snapshot shape) was also run directly. Full
Python compile and JS syntax sweep clean. The GitHub push itself was
verified by reading the pushed commit back from the API afterward, not
just trusting `git push`'s exit code.

## Shipped in 0.11.14: 0.11.13's fix was real but incomplete -- network devices had the same gap

Rob installed 0.11.13 and reported items were still coming back. Took that
at face value rather than assuming the previous fix covered it, and found
a second, genuinely separate hole in the same fix.

0.11.13's `warmed_up()` gated on the five `PeriodicMonitor` checks (health,
events, tune-up, drives, thermal) before letting anything resolve. It
missed two sources that feed the Advisor but aren't `PeriodicMonitor`s at
all, so nothing was gating them:
- **Network.** `NetworkBuilder` runs on its own loop with its own
  first-build delay (`self.network_at` starts `None`). Until that first
  scan completes, `network_rules()` sees an empty device list and reports
  nothing -- so a snoozed or previously-seen "unknown device" alert was
  exactly as exposed to the same false-resolve-then-reborn-as-New pattern
  as the Tune-up items 0.11.13 fixed. Reproduced this specifically: a
  *snoozed* (not even just kept) `unknown-devices` alert flipped to
  resolved after two empty evaluate() cycles during the network startup
  gap, before 0.11.14's fix; confirmed it now survives that gap and a
  genuine snooze/no-change afterward, using the same real `AlertManager` +
  `History` classes as before, not a mock.
- **System vitals.** `SystemMonitor` waits one `SAMPLE_SECONDS` (2s) before
  its very first reading -- a much shorter window than the other two, but
  real, and the NVIDIA-driver-check reminder (`driver-check`, a "Keep as
  is"-able item) depends on it having sampled at least once.

`Monitor.warmed_up()` now also requires the network's first build and
(when vitals are available at all) the system monitor's first sample
before treating anything as possibly resolved.

**Honest caveat, unprompted:** this fix only stops *future* false-resolves.
If any item already got wrongly reset to "New" by the bug before 0.11.14
was installed, that already happened -- 0.11.14 doesn't retroactively
un-reset it. If something still looks freshly "New" right after updating,
that's expected once, from before the fix; if it happens *again* on a
*later* restart after that, that's a sign there's a third gap still
uncaught, not a sign this fix didn't work. Flag that specifically if it
happens, since "did it recur after this version, on a restart after the
first one" is the actual test, not "does it still look New immediately
after updating this one time."

Verified: reproduced the network-specific case directly (see above) before
and after the fix, plus the general `warmed_up()` logic unit-tested across
all five combinations of "one source not ready" (each of the five periodic
checks, network, and system unavailable-vs-not-yet-sampled). Full Python
compile and JS syntax sweep clean. Same limitation as 0.11.13: this is a
simulated-timing reproduction against the real alert-lifecycle code, not a
real Windows restart, since this sandbox can't do that.

## Shipped in 0.11.13: the real "keeps popping back up" bug, and Windows Update failure detection

Rob asked for a second, fresh pass through the efficiency report, then flagged
something separate while looking at a screenshot: "these same things pop up
with every new edition regardless if i have muted or ignored them." That's
not what "New edition" *should* do -- Program and Data folders are kept
deliberately separate (see paths.py) specifically so an update never touches
your snooze/keep decisions. Went looking for why it looked like it did anyway.

**Found and fixed a real bug, reproduced before touching any code:**
`alerts.py`'s lifecycle marks an item "resolved" once it's been missing from
the Advisor's suggestions for 2 evaluation cycles in a row (20 seconds,
since the Advisor re-evaluates every 10s) -- and once something's "resolved,"
the next time it reappears it's raised as brand-new, with none of its
history. That's the right behavior for a condition that actually went away.
The bug: several background checks (Tune-up especially) can take up to a
*minute* to complete their first read after Matrix starts -- and Matrix
restarting is exactly what happens on every update. So for that startup
window, anything depending on those checks (the battery power-plan warning,
the GPU-mode reminder, the startup-apps count, more) is briefly *absent* from
the Advisor's suggestions -- not because the situation changed, but because
the check simply hasn't reported back yet. 20 seconds of that was enough to
flip a "Keep as is" or a snooze to "resolved," and then straight back to
"New" the moment the real check caught up a bit later -- discarding the
decision, every single restart. Reproduced it directly against the real
`AlertManager`/`History` classes (a "kept" item flipped to "resolved" after
two 10-second-apart empty evaluations, then came back as active/New) before
writing the fix, then re-ran the same reproduction against the fix to
confirm it holds while a genuine resolution (the condition actually gone
while everything's warmed up) still works normally. Fix: `Monitor` now
tracks whether every background check has completed its first real read
since this run of Matrix started (`warmed_up()`); `alerts.py` no longer
treats an item as possibly-resolved until that's true. This should be the
actual fix for the "keeps repeating" pattern Rob flagged back in 0.11.10 --
that session's dig through `alerts.py` didn't find a bug because the
startup-window race wasn't happening in the moment being tested; this time
it was caught with a direct, repeatable simulation.

**New coverage, from the efficiency report's leftover options (picked
"update-failure detection" as the lowest-cost, highest-value one):**
- [x] Windows Update can now tell "hasn't had a new patch to offer" apart
      from "has been failing every attempt." `Get-HotFix` (the existing
      source for "last update was N days ago") only ever lists updates that
      *installed successfully* -- a PC stuck failing every attempt looks
      identical to one that's simply current. Added a read of the Windows
      Update Agent's own history (`Microsoft.Update.Session`, a documented,
      unelevated COM API), which records the real result of the most recent
      attempt. If that most-recent attempt failed and it's been 2+ days
      (giving Windows' own automatic retry a chance first) with nothing
      successful since, Matrix now says so specifically, rather than just
      reporting the same "N days since last update" either way.

Talked through the other three leftover options (CPU temperature, backup
status, BIOS/firmware tracking) with Rob rather than building blind:
CPU temperature would mean either running Matrix itself elevated or adding
a second always-on elevated helper process, a real, one-way architecture
change to an app that currently needs zero admin rights for anything --
tabled for now, not ruled out forever. Backup status and BIOS tracking are
both cheap to add but weren't picked this round; still on the list for
whenever Rob wants them.

Verified: reproduced the warmup-race bug against the real `alerts.py` +
`history.py` classes before fixing, confirmed the fix holds while genuine
resolution still works, and unit-tested `Monitor.warmed_up()`'s gating logic
directly. The new `update-failed` rule was tested against recent-success,
failed-and-old-enough, failed-too-recently, and not-yet-checked cases. All
Python compiles clean; all JS passes `node --check`. Not verified against a
real Windows Update history or a real restart-during-startup race, since
this sandbox has neither -- the reproduction used the same classes Matrix
runs, with simulated timing standing in for a real slow Tune-up check.

## Shipped in 0.11.12: an efficiency pass -- drive health, a cooling-trend proxy, and trimming real waste

Rob asked for a fresh-eyes efficiency review: what's missing, what's being
wasted, how to best run and maintain this laptop long-term. That report
turned into a prioritized list Rob picked from directly. This batch is
those picks.

**New coverage:**
- [x] **Drive health (SMART-style).** New background check (`drive_health.py`)
      reads Windows' own Storage Management API (`Get-PhysicalDisk` /
      `Get-StorageReliabilityCounter`) -- no vendor tool, no extra install.
      Reports each physical drive's overall health status (Healthy / Warning /
      Unhealthy), plus wear %, temperature and error counts where the drive
      exposes them (not every controller/drive does). New Advisor rules flag
      a non-healthy drive or one that's 80%+ through its rated write
      endurance -- something the existing free-space checks would never
      catch, since a drive can be nearly empty and still be dying. Also
      surfaced directly on the Tune-up page as a "Drive health" card, so a
      healthy drive shows a plain green confirmation instead of only ever
      speaking up when something's wrong.
- [x] **Cooling trend (dust/fan proxy).** New `thermal_trend.py` watches the
      GPU temperature system.py already samples every couple of seconds, but
      only records it when the PC is genuinely idle (low CPU and GPU load at
      the same time) -- keeps the coolest reading seen each day, persisted to
      disk so it survives restarts. Once there are at least 14 days of idle
      samples, it compares the older half of the record against the newer
      half; a resting-temperature rise of 8°C+ raises an Advisor item
      (12°C+ is critical), also shown plainly as a "Cooling trend" card on
      Tune-up. **This is an honest proxy, not a fan-RPM sensor** -- Windows
      exposes no standard API for actual fan speed, and the vendor SDK that
      does (Armoury Crate's telemetry) isn't something Matrix wants to
      depend on. Room temperature, where the laptop physically sits, and
      driver/firmware changes can all move idle temps too; the card and the
      Advisor note both say so rather than pointing straight at dust.

**Cleanup (real waste, not "cut things to save resources"):**
- [x] **Fixed the GPU-mode nag repeating forever.** Its fingerprint used to
      embed the ISO week number, which meant it changed every single week no
      matter what -- and `alerts.py` treats a changed fingerprint as "the
      situation changed," which silently overrode "Keep as is" or a snooze
      every 7 days, forever. Gave it a stable fingerprint instead. Matrix
      still can't see which GPU mode Armoury Crate has active (no standard
      Windows API exposes it), so the note itself is unchanged -- only the
      repeat-every-week bug is fixed.
- [x] **Removed Windows-health data that was collected but never read
      anywhere:** Defender's `AntivirusEnabled` / `IsTamperProtected` fields
      (only `RealTimeProtectionEnabled` was ever checked), the Windows
      Update `HotFixID` (only the date was used), and the entire
      `Get-NetConnectionProfile` query (a real separate PowerShell call,
      run every 5 minutes, whose result no rule or view ever looked at).
      Confirmed via grep across `server/` and `js/` before removing each one.
- [x] **Slowed down two background checks that were running far more often
      than their data changes:** the passive network rescan went from every
      5s to every 20s (still instant on demand -- opening a device, hitting
      "Check again," anything interactive calls the fast path directly and
      isn't affected), and Tune-up's background scan (startup apps, temp
      files, battery health, power settings -- all things that change over
      days, not minutes) went from every 30 min to every 60 min. "Check
      again" in the UI still forces an immediate run on both, regardless of
      the background interval.

Not done this batch, carried to 0.12: the idea (from the same efficiency
report) of using Windows' own Disk Cleanup / driver-store data automatically
is still manual-only -- Rob's doing it by hand for now (41.6 MB reclaimed on
his first pass). Automating that safely is a bigger job than this batch had
room for.

Verified: every changed Python file compiles; every changed JS file passes
`node --check`; `drive_rules()` and `parse_drives()` (drive health) and
`thermal_rules()` plus `ThermalTrendMonitor`'s recording/trend math (cooling
trend) were each unit-tested directly against healthy/warning/unhealthy/
high-wear/no-data cases and rising/flat/insufficient-history cases; the new
Drive health and Cooling trend cards were rendered headlessly against a mock
state (one healthy SSD, one Warning HDD, an 8°C idle-temp rise) and checked
both by reading the generated HTML and by screenshot -- both cards render
correctly and match the existing Tune-up page's look. Not verified against a
real Windows machine or real SMART/thermal data, since this sandbox has
neither -- that first real read happens on Rob's laptop.

## Shipped in 0.11.11: the actual jump (not the timing bug), and an auto-hide scrollbar

Rob wasn't crazy -- 0.11.8's timing-bug fix was real, but it wasn't the
whole story, and his next recording still showed a visible jump. Went
looking again instead of assuming the earlier fix covered it.

Found it with a hard measurement, not a guess: wrapped `Math.random()` with
a counter and watched it across live poll cycles. Result: **~15,324 calls,
every single poll (every 3 seconds), forever** -- the signature of a full
rebuild of all 3,200 particles from scratch, at a fixed 3-second cadence
completely unrelated to the animation's own frame rate.

Root cause, in `livingCore.js`: Overview rebuilds its entire HTML from
scratch on every poll (documented already, elsewhere in this file), which
means the `#living-core-mount` placeholder div is a brand-new DOM node every
time. `mount()` re-parents the persistent canvas into it whenever the
container isn't already its parent -- which, given the above, is *every
single poll* -- and `mount()` called `_resize()` unconditionally on every
re-parent. `_resize()` in turn called `_buildParticles()` unconditionally
too. So the entire star field was thrown away and re-randomized every 3
seconds, regardless of whether the canvas had actually changed size. That's
a real, visible "jump" -- the whole scene reshuffling -- happening in
lock-step with the server poll, not with anything about the rotation speed.
This was a genuinely different bug from 0.11.8's timing fix, not a
continuation of it; both were real and both needed fixing.

- [x] Fixed: `_resize()` now compares the new canvas dimensions against the
      current ones and returns immediately if nothing actually changed, so
      a same-size re-parent (every poll) is now a no-op, and only a real
      size change (first mount, an actual window resize) rebuilds particles.
- [x] Verified with the same `Math.random()` counter: 0 calls across two
      full poll cycles after the fix, versus ~15,324 per cycle before.

Also, since Rob asked for it directly: **the scrollbar now only shows up
while actively scrolling.** It used to sit on screen permanently (a
deliberate earlier fix, but "always visible" isn't the same as "auto-hide,"
which is what was actually wanted). `js/app.js` now listens for `scroll`
events (capture phase, since `scroll` doesn't bubble) and adds an
`is-scrolling` class to `<body>` for ~900ms after the last scroll event;
`css/styles.css`'s scrollbar thumb is transparent by default and only fades
in while that class is present. Verified headlessly: absent before
scrolling, present immediately after a scroll event, gone again ~1s after
scrolling stops.

## Shipped in 0.11.10: naming exactly which setting "maxed out on battery" means

Rob said the battery power warning ("The processor can run at full power
even on battery") keeps showing up, but Windows' own Settings app shows his
power plan as "Balanced," both plugged in and on battery -- so either
Matrix is wrong, or it's talking about a setting he isn't looking at.

Checked the actual collector (`tuneup.py`'s PowerShell block): it runs
`powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX`, which reads
the **currently active** plan (not a hardcoded one), and specifically the
"Maximum processor state" percentage on battery -- that's correct as
written, no bug found there. The likely real explanation: this is a
different, deeper setting than the one Rob's checking. Windows' Settings
app shows a simple plan name/slider ("Balanced"), but "Maximum processor
state" lives one level down, under Power Options -> Change plan settings ->
Change advanced power settings -> Processor power management -- and it's
entirely normal for Windows to leave that at 100% even while the plan
itself is "Balanced." They're two separate settings that just happen to
share a name in casual conversation.

- [x] Made the warning say so explicitly instead of leaving Rob (or anyone)
      to guess: it now names the exact plan Windows reported ("Balanced" or
      whatever it actually is), states the deeper setting and its actual
      path in Windows, and says outright that it's a different setting from
      the plan name. Verified by calling `advisor.tuneup_rules()` directly
      with fake data and confirming the exact text produced.
- [ ] Went looking for a "keeps repeating" bug specifically -- reread the
      whole alert lifecycle in `alerts.py`. Once raised, this item's
      fingerprint is a constant string, so on every normal re-evaluation it
      just refreshes in place (`_update_present`'s active branch) without
      re-raising, re-notifying, or re-tagging "New". I could not find a code
      path that would make an unchanged, still-true item nag repeatedly.
      **Being honest instead of guessing a fix for a bug I couldn't find:**
      if it's genuinely reappearing as "New" repeatedly (not just still
      sitting there because it's never been addressed), the most likely real
      cause on this specific machine is Armoury Crate itself changing the
      actual Windows power plan when it switches Silent/Performance/Turbo
      modes -- which would make the underlying setting genuinely flip
      between maxed/not-maxed, and Matrix would be correctly reporting a
      state that's actually changing, not showing a stale warning. This
      already lines up with the standing note lower in this doc about
      Armoury Crate mode-switching being outside Matrix's control for now.
      If it's still doing this on 0.11.10, the "Snooze 1 week" or "Keep as
      is" buttons on the card will stop the nagging regardless of cause --
      but tell me if either of those isn't sticking, since that would be a
      real, different bug.

## Shipped in 0.11.9: MOMUS actually gets to talk now

Rob asked directly: what about the other one -- the nemesis persona, the one
originally requested as an Ultron stand-in and shipped instead as MOMUS
(original character, not licensed -- see HANDOFF.md's IP boundary note)? He
was right to ask. `server/persona.py`'s own module docstring already
promised MOMUS would be "critical items only (and a rare swap-in
elsewhere)" -- but that "elsewhere" was never actually built. Every
non-critical branch in `card_voice()` hardcoded ARGUS unconditionally, and
`MOMUS_LINES` only had two banks (`critical`, `resolved`) with two lines
each -- four lines total in the entire app, reachable only on a critical
item, and only 35% of the time even then. For a typical home setup where
most Advisor items are "attention"/"fyi", not "critical", MOMUS was
effectively never seen. That's not a persona-voice bug, it's a feature that
was designed but never finished.

- [x] Gave `MOMUS_LINES` real `new`, `snoozed_repeat` and `still_open` banks
      in his own voice (entertained by the user's misfortune, talks like
      small daily problems barely register next to what he's actually seen
      go wrong) -- distinct from ARGUS's dry, keeping-score tone.
- [x] Wired him into the actual selection logic for every bucket, not just
      critical (`MOMUS_CHANCE = {"critical": 0.35, "snoozed": 0.3, "stale":
      0.3, "new": 0.15}` -- ARGUS stays the default voice everywhere, as the
      docstring says, but MOMUS is now a real, recurring presence instead of
      a near-unreachable cameo).
- [x] Kept `card_voice()` (the instant quip badge) and `voice_for_ai_note()`
      (which persona the local AI writes the longer note as) using the exact
      same seeded selection, so they never disagree about who's "speaking"
      for a given card -- verified with a script calling both directly.
- [x] Punched up MOMUS's AI style prompt to match the sharper voice.
- [x] Verified deterministically: ran `card_voice()` against 200 synthetic
      "new" items, confirmed MOMUS shows up at roughly the designed rate
      (not 0%, not dominating), confirmed his actual lines read distinctly
      from ARGUS's, and confirmed zero disagreements between the quip badge
      and the AI-note voice picker across 200 more.
- [ ] Same honest caveat as 0.11.8's AI-note change: the deterministic quip
      lines are fully verified, but whether MOMUS's *AI-written* paragraphs
      (the local model's prose, not the canned quip) actually sound
      different from ARGUS's can't be confirmed without Rob's real Ollama
      model running -- flag it if his notes still all sound the same.

## Shipped in 0.11.8: the actual animation bug, and ARGUS getting his voice back

Two real, separately-confirmed fixes from Rob's next two recordings.

**1. The Living Look animation was never actually broken by throttling -- it had a
genuine timing bug from the start.** Every previous "fix" to animation speed
(the loop-snap fade, the unfocused-window dt clamp) was real but none of them
were the actual cause of it looking slow and jumpy. The real bug, in both
`livingCore.js` and `livingBackground.js`:

```js
_loop(now) {
  if (!this.running) return;
  this.last = now;        // <-- sets this.last to the CURRENT frame's time
  this._frame(false);     // <-- which _frame() then diffs against a fresh
  ...                      //     performance.now() call, taken a moment later
}
```

`_frame()` computes `dt` by reading a fresh `performance.now()` and comparing
it to `this.last` -- but `_loop()` was setting `this.last` to *this exact
frame's own timestamp* immediately beforehand, so every single frame's `dt`
came out as the time between two clock reads a fraction of a millisecond
apart, essentially zero forever. Proved this outside the browser first: a
plain-JS simulation of the exact same two methods, fed 5 seconds of
regularly-spaced frame timestamps, produced a clock that had advanced by
`0.0000` instead of ~5.0. That's why it read as "slow" (the animation's
internal clock barely moved) and "jumpy" (browsers don't guarantee
`performance.now()` returns a different value on two reads microseconds
apart -- when it doesn't, that frame is perfectly frozen; when the reads
happen to straddle a resolution step, you get one real tick of movement,
which is what shows up as a jump against an otherwise static scene).
- [x] Fixed: removed the `this.last = now` line from `_loop()` in both files.
      `_frame()` already updates `this.last` correctly right after using it.
- [x] Verified: pixel-sampled the actual canvas every 0.5s over 3 seconds
      against the real front-end code and confirmed it now changes
      meaningfully every step, instead of sitting nearly static.

**2. ARGUS had no attitude on the single most common card state.** Rob's
screenshot showed a totally flat, personality-free line: "New: The processor
can run at full power even on battery." Checked `server/persona.py`'s quip
banks -- `critical`, `snoozed_repeat`, `still_open` and `resolved` all have
real dry wit, but `new` (the one almost every card actually uses, since most
items are neither critical, snoozed, nor a week old) was written as bare
templates with zero personality: `"New: {title}."` / `"{title}. Added to the
list."` That's not a persona bug, it's a content gap -- the bank that gets
seen the most was never actually written in ARGUS's voice.
- [x] Fixed: rewrote the `new` bank with actual ARGUS lines. Verified
      deterministically (no AI needed for these -- they're the canned
      quip bank, not AI-generated) by calling `persona.card_voice()`
      directly with Rob's exact item and confirming real attitude comes out.
- [~] Also strengthened the wording Matrix sends to the local AI for the
      longer "ARGUS SAYS" note (the AI-generated paragraph below the quip
      line) -- the system prompt's "be plain-spoken" rule and the per-item
      prompt's "plain English" wording were both competing with the persona
      instruction, likely burying it. **Not independently verified** -- this
      sandbox has no way to run Rob's actual local model (qwen3:8b via
      Ollama) to confirm the tone actually comes through stronger now. This
      is a good-faith improvement to the prompt, not a proven fix; if the
      "ARGUS SAYS" paragraphs are still flat after this, say so.

## Shipped in 0.11.7: a second, different cause of the stuck footer

Rob installed 0.11.6 and sent two recordings. The first, taken right after
opening the app, still showed "Waiting for Matrix..." forever, no version
number, and system vitals (CPU/GPU/memory) stuck on "-", even though the
network device count and "All systems nominal" status *had* loaded. The
second, taken about two minutes later, showed everything working perfectly
-- real CPU/GPU/memory numbers, "● Live · Matrix 0.11.6" in the footer. That
gap is what cracked this one open: it wasn't stuck forever, it only *looked*
permanently stuck, and only right at startup.

Root cause, found in `server/system.py`: the vitals sampler reports
`available: true` as soon as `psutil` imports successfully, but the actual
readings (`cpu`, `memory`, `disks`, `gpus`...) only show up a couple of
seconds later, once its background sampling loop completes its first pass
-- and if that pass keeps failing for any reason, they never show up at
all. So there's a real window (usually ~2 seconds, but open-ended if
sampling keeps failing) where the server correctly reports "available" but
has no actual numbers yet. The front end's `renderMeters()` in `js/app.js`
didn't plan for that combination: it assumed `available: true` meant
`system.cpu.usage` was safe to read directly, and reading `.usage` off a
`system.cpu` that doesn't exist yet throws.

That alone would just be a one-frame glitch. What turned it into a
permanent freeze is `js/services/dataService.js`'s poll loop: it calls
every subscribed listener and only *then* schedules the next poll. An
uncaught exception partway through that render call aborted the whole
callback -- including the line that schedules the next fetch -- so the
entire polling loop quietly died, for good, the very first time this raced.
Confirmed headlessly: served exactly this state shape (`available: true`,
no `cpu`/`memory` yet) for the first two polls, then switched to full real
data for every poll after -- before the fix, the dashboard stayed on
"Waiting for Matrix..." forever even 14+ seconds after good data started
being served; after the fix, it recovers normally.

- [x] Fixed `renderMeters()` to read every field defensively (`system.cpu?.usage`
      etc.) and show "n/a" for whichever fields aren't in yet, instead of assuming
      `available: true` means the whole shape is populated.
- [x] Fixed the poll loop itself so this class of bug can't cause a permanent
      freeze again: each listener call in `dataService.js` is now wrapped in its
      own try/catch, so one bad render logs a console error and gets skipped,
      but the next poll is still scheduled. This is a defense-in-depth fix, not
      just a patch for this one field -- any future rendering bug hitting an
      unexpected state shape will now show up as a one-frame glitch instead of
      a silent, permanent freeze.
- [x] Verified: reproduced the exact freeze headlessly first (confirmed the
      `Cannot read properties of undefined (reading 'usage')` error and the
      permanent stuck footer), then confirmed the fix resolves it and the
      dashboard recovers on its own once real data arrives. Full JS/Python
      compile checks and the real-data regression test all still pass.

## Shipped in 0.11.6: the real cause of "dashboard won't populate"

This is the fix for the whole evening's "Waiting for Matrix..., no version, no
CPU/GPU/network info" saga -- and it turned out to have nothing to do with
animation, stale windows, zombie processes, or the Jetwriter extension (all
ruled out one at a time on Rob's evidence before this was found).

Root cause: `server/matrix_server.py` was serving the app on Python's plain
`http.server`, which defaults to a `listen()` backlog of only **5** pending
connections. The dashboard's first load fires off roughly 30 requests at once
(every view's own script file, fonts, the manifest, icons...). Past 5
simultaneous connection attempts, the OS just refuses the rest outright and
silently -- no error on the server side, no exception, nothing to catch. On a
machine that's a little slower to service each request (background load,
antivirus scan, whatever), it's easy to blow through 5 immediately.

The part that made this so confusing to chase: `app.js` statically imports
every view module together at the top of the file. If even *one* of those
~14 files gets refused, the whole import fails, which means **none** of
`app.js`'s code runs at all -- not the state poller, not the error handlers,
nothing. That's exactly what we saw: a dashboard stuck on its very first
paint, no Matrix-code JS errors ever appearing in the console (there's no
code left running to throw one), while manually visiting `/api/state`
directly always worked fine, because that's a single request, not a burst of
30. It also explains why results were inconsistent between attempts -- which
~14 of the 30 requests got refused was effectively random each time.

Rob's own Network tab screenshot is what nailed this down: 14 requests
showing `net::ERR_CONNECTION_REFUSED`, all of them view/component script
files, while every other request (API calls, CSS, fonts, icons) succeeded.

- [x] Fixed: added a `Server(ThreadingHTTPServer)` subclass in
      `matrix_server.py` with `request_queue_size = 128` set as a *class*
      attribute (has to be a class attribute -- `TCPServer.__init__` calls
      `listen()` synchronously during construction, so setting this on the
      instance afterward does nothing; caught that mistake myself by reading
      Python's `socketserver` source before shipping it).
- [x] Verified: full JS syntax check (`node --check` on every file) and
      Python compile check both clean; re-ran the real-data mock-server
      regression test (`rob_repro.py`, using Rob's actual pasted `/api/state`
      JSON) and confirmed version, footer, CPU and online-device-count all
      still populate correctly with no functional JS errors.
- [ ] Honest caveat: a synthetic 30-connections-at-once test in this sandbox
      did not reliably reproduce refusals even at the old backlog of 5 (this
      environment's thread scheduling accepts connections faster than a real
      busy Windows machine would), so this fix is verified by reading and
      fixing the actual mechanism (Python's documented `listen()` backlog
      behavior) plus Rob's own Network tab evidence, not by a load test that
      reproduces the failure end-to-end. If Rob still sees any
      `ERR_CONNECTION_REFUSED` entries in Network on 0.11.6, that means there's
      a second contributing factor and this isn't the whole story -- don't
      assume it's closed until he confirms.

Also in 0.11.6: removed a wasteful per-poll rebuild of the Living Look's
~3,200 background particles (`_buildParticles()` was being called on every
state poll, roughly every 2-3 seconds, even though the particles' weights
never change after the canvas is sized -- it now only runs on resize). And
raised the animation `dt` clamp in both `livingCore.js` and
`livingBackground.js` from 0.05s to 0.5s per frame -- Chrome throttles
`requestAnimationFrame` hard for a window that's visible but not focused
(sitting next to whatever window you're actually using), and the tighter
clamp was turning that into visible slow-motion instead of just fewer,
larger animation steps.
- [ ] "Background lines should have much smoother animation" -- still open,
      no concrete cause identified yet. Worth watching whether the dt-clamp
      change above helps, since an unfocused window was one real source of
      visible slowdown, but don't claim this closes it without Rob saying so.
- [ ] "Stop Matrix" button not appearing to do anything -- still open, not
      yet investigated. `js/views/settings.js`'s `quit()` uses a `confirm()`
      dialog; worth checking whether that's even firing.

## Shipped in 0.11.5: scroll position jump on Overview

Rob's screen recording showed the Overview page jumping back to the top after
scrolling down and stopping. Found a real cause (there may be more than one --
see below): every poll rebuilds the *entire* Overview page from scratch
(`root.innerHTML = ...` in `js/views/overview.js`, not a diff/patch), including
a fresh, empty `#living-core-mount` placeholder div. `js/app.js`'s `renderView()`
was restoring the saved scroll position right after that rebuild, but *before*
`livingCore.mount()` re-inserted the actual scene (a tall canvas) into that
placeholder. So scroll got restored while the page was still short (placeholder
empty), and a moment later, when the real scene popped in and the page grew
underneath the scroll position, Chrome's own scroll-anchoring shoved the
viewport around to compensate -- confirmed in a headless test: scrolling down,
waiting through a couple of poll cycles, and watching scrollTop jump on its own
by hundreds of pixels with no user input.
- [x] Fixed: `view.scrollTop = scroll` now runs *after* the Living Look scene is
      remounted, once the page's real height for this poll is settled, not before.
      Verified with a headless test that scrolls, waits through 10+ poll cycles,
      and confirms scrollTop no longer drifts on its own.
- [ ] Not fully confirmed as the *only* cause -- Rob's report was specifically
      about clicking the browser's native scrollbar down-arrow button and then
      it snapping to the top, which I couldn't reproduce exactly headless (only
      reproduced a jump-down, not jump-to-top). That native button is also
      exactly what 0.11.4 already removes (`::-webkit-scrollbar-button` fix),
      so it's possible Rob was still on an older build when he recorded this.
      If the page still jumps after 0.11.5 on the actual machine, say so --
      don't assume this closes it out.

## Shipped in 0.11.4: scrollbar + Living Look polish, and the green title bar explained

Rob sent screen recordings of 0.11.3 still running. Two real fixes, and one thing
that turns out isn't Matrix's to fix:
- [x] The themed scrollbar (added in 0.11.2) only recolored the thumb and track,
      not Chrome's own up/down arrow buttons at each end -- those kept rendering
      as plain OS-gray squares sitting right against the thin cyan thumb, which
      is what read as "glitchy." `::-webkit-scrollbar-button { display: none }`
      removes them everywhere.
- [x] The traveling dot on each satellite connector line (Network, Performance,
      Security, etc., pulsing in toward the sphere) ran on a ~2.9s loop with no
      fade, so every lap it hit the end of the line and instantly teleported
      back to the start -- a visible snap once you noticed it, exactly Rob's
      "loop is only like 2 seconds" report. Fixed with a sine fade envelope (the
      dot is invisible right at the loop point, both ends) plus a slightly
      slower pace (~4.5s), in `js/components/livingCore.js`.
- [x] Checked for a real cause of the green title bar and ruled Matrix's own
      code out completely: `index.html`'s theme-color, `manifest.webmanifest`,
      and all three icon files are confirmed navy/cyan (no leftover #36e2b4
      anywhere), and `server/desktop.py` never sets a window/caption color --
      it only calls `chrome --app=<url>`. A solid color band across the *whole*
      title bar (not just an icon) matches Windows' own "show accent color on
      title bars" setting (Settings -> Personalization -> Colors), which paints
      every app window that way regardless of the page underneath. Told Rob to
      check that setting/his current accent color rather than shipping another
      guess at a code fix for something outside the app's window.
- Not fixed / not verified: Rob also said the flowing background lines "should
  have much smoother animation." That's a real, standing perf/feel ask (the
  background canvas draws 18 multi-fiber strands + 8 traces every frame), not
  a bug with a specific cause found yet -- worth profiling actual frame times
  on Rob's machine before changing anything, rather than guessing at a fix.

## Shipped in 0.11.3: fixed the 0.11.2 freeze

0.11.2 shipped a real bug: `js/components/livingCore.js`'s `update()` declared
its `online` device count inside the `if (away) {...} else {...}` branch added
for the away-from-home work, then referenced it again further down (in the
scene's subline) outside that block. That's a `ReferenceError` on every single
call -- which happens every ~3 seconds, on the Overview page, with Living Look
on (the default). Because it threw partway through the shared render function,
*nothing* past that point ever ran again: the version, device count, Advisor
panel, and system meters all stayed frozen at their very first paint, forever,
even though the server underneath was working fine the whole time (confirmed
via "Copy diagnostics", which reads server state directly rather than going
through the broken render path).
- [x] Fixed: `online` is now computed once, outside the away/not-away branch,
      so it's in scope everywhere it's used.
- [x] Added a real regression test for this class of bug: a headless-browser
      check that loads the Overview page in all three states (Living Look on
      + normal, Living Look on + away, Classic) and fails if the console logs
      *any* JS error, not just if a screenshot looks visually wrong. This is
      exactly the gap that let 0.11.2 ship broken -- prior checks only
      confirmed things *looked* right, not that nothing quietly threw.

## Shipped in 0.11.2: Away from home

Rob's report: on his school's wifi, Matrix was still listing/flagging other
devices, which felt like it was scanning a network it had no business
watching. The scan itself was already passive (it only reads the OS's own
ARP cache -- it never pings or probes anyone else's device), but the
dashboard still showed and flagged whatever the OS already knew about,
wherever you were.

- [x] Automatic: "Trust all current devices" now also remembers this
      network's router (its MAC), so Matrix learns what "home" is. Any time
      the current router doesn't match, Matrix stops reading, listing or
      flagging every other device on that network -- automatically, no
      toggle needed -- and only keeps watching this PC.
- [x] Manual override in Settings: "Pause device scanning right now," for
      before a home baseline is set, or to force it even on a network
      Matrix would otherwise treat as familiar.
- [x] The Network view, the Overview network card, and the Living Look's
      network satellite all explain the paused state plainly ("Away from
      home network") instead of just showing a sparse or empty list.
- [x] Turning it back off (manually, or by returning to the home router)
      picks scanning back up right away -- no restart needed.
- [x] Leftover-green cleanup: the Network view's map still had its old,
      pre-mockup teal-green grid background and a scanning-CRT-line effect
      left over from before the navy/cyan palette rewrite -- along with a
      handful of the same leftover teal-green in sparkline fills, chat
      bubbles, active tabs, table-row hover, and (the real culprit behind
      the green title bar/window icon) the app's own icon files
      (`icons/matrix-192.png`, `matrix-512.png`, `matrix.ico`), which were
      still the old teal-green "M" mark. All of it is now the same navy/cyan
      "no boxes" treatment as the rest of the app.
- [x] Network map makeover: replaced the rigid grid-of-straight-lines
      topology with soft S-curve connectors (matching the Living Look's
      satellite-link style) and a shallow arc per row instead of a flat
      line, plus a slow-spinning dashed orbit ring on each device -- the
      map itself now uses the same translucent "no boxes" backdrop as other
      data-dense cards instead of a boxed grid.
- [x] Type-tinted glass nodes: Rob reviewed three node-style directions on a
      design canvas (gradient orb, type-tinted glass, vivid filled) and
      picked type-tinted glass. Each device type now gets its own
      translucent color (computer/laptop cyan, phone/tablet indigo,
      entertainment pink, printer/NAS gold, smart-home purple) with a glass
      ring and a small specular highlight; offline and threatened devices
      still override to gray/red regardless of type. A legend sits under the
      map. Also renamed the phone glyph from "MOB" (easy to misread) to
      "PHN".
- [x] Themed scrollbars: the OS's default chunky light-gray scrollbar is
      replaced everywhere with a thin, dark, accent-colored one that matches
      the rest of the app.

## Shipped in 0.11.1: Living look, done properly

0.11.0's first pass at this (below, superseded) was built off a text description of the
Living Look instead of the actual reference file already sitting in the project,
`design/matrix-living-core.html` -- a fully-built concept page, not a rough sketch. This
release replaces that first attempt with a real port of that page's canvas engine,
wired to live data. That file is the standard to match on any future visual work here,
not the roadmap prose describing it.

Rule for every item, still true: looks never cost information. Anything pretty must
still show exact numbers one click (or one glance) away, and never slow the PC down.

- [x] The whole app now uses the mockup's actual look: navy/cyan/gold palette
      (`#020817` / `#5fd4ff` / `#f5d27a`), Saira/IBM Plex Sans/JetBrains Mono, "no boxes"
      (panels have no background or border of their own; text sits on the flowing
      background with a text-shadow instead) -- not just the Overview, every view
- [x] A real canvas particle sphere (not CSS/SVG) rotating in 3D, with six satellite
      nodes -- Network, Performance, Security, Crashes, Tune-up, Matrix AI -- each with
      an orbit ring, a curved connector line with a traveling data dot back to the core,
      and a live status line, all from real state (device count, CPU/GPU/temp, Windows
      protection, crashes this week, flagged tune-up items, AI activity). Click a node
      to jump to its view; critical items turn a node red and pulse it faster
- [x] Full-page flowing background canvas: circuit traces with traveling dots, and
      strand bundles that ripple and bend toward wherever the living core currently sits
      (or screen center on other views) -- the lines' own shape moves every frame, not
      dashes sliding along a static line
- [x] Particle bursts for genuinely new timeline items, capped so a busy period never
      floods the scene; a legend explaining what the particles mean
- [x] The rail grew a live system-meters strip (CPU / GPU / GPU temp / Memory / Disk),
      thin glowing bars matching the mockup, fed by the same live vitals as Performance
- [x] Status colours (critical, warning, OK) never changed -- same meaning everywhere,
      just the mockup's exact shades
- [x] Animation pauses when the tab is hidden, throttles when the GPU is already busy
      (>85% usage), and follows `prefers-reduced-motion`; a pause-motion button on the
      scene itself, remembered per browser
- [x] Settings: Living (default, the full scene) or Classic (plain card grid, no scene --
      the flowing background and palette stay either way, since panels being boxless is
      now how the whole app looks, not an Overview-only extra)
- [ ] A live events feed and a red-alert banner overlay, both present in the mockup, were
      left out of this pass -- the existing Advisor panel and Timeline view already cover
      that ground reasonably and duplicating it felt like scope creep; revisit if it's
      still wanted once the rest has been lived with a bit

<details>
<summary>Superseded: 0.11.0's first attempt (kept for the record, not the standard to match)</summary>

Built from a text description instead of the actual mockup file -- a CSS/SVG ring
widget scoped to the Overview card grid, with opaque panels kept everywhere else. Fully
replaced by the above; nothing from this attempt survived except the settings toggle and
pause-button ideas, which 0.11.1 kept.
</details>

## Ideas from research (Sep 27): to place into batches

Look and feel
- [ ] Colour themes on top of the living look (Synthwave, Grid, Phosphor, etc.; mockups
      exist). Lower priority now that the living look is the direction.
- [ ] Compact HUD mode: a small always-on-top window (or a cheap 3.5" USB sensor screen)
      with gauges and the top alert, like AIDA64 sensor panels
- [ ] Optional sound effects (eDEX-UI style), off by default

More (and fresher) information
- [ ] CPU temperatures via LibreHardwareMonitor (needs a small elevated helper)
- [ ] Passive device names: listen for mDNS / SSDP announcements (what NetAlertX does),
      no probing needed, much better identification of phones, TVs and speakers
- [ ] Connection map: where this PC's connections go in the world (offline GeoIP list)
- [ ] Relevant news feed (Glance-style): Patch Tuesday, NVIDIA driver releases, actively
      exploited vulnerabilities (CISA KEV) that match software on this PC
- [ ] Phone notifications for critical items via ntfy (opt-in; vague message text,
      private topic or self-hosted server, since messages pass through that server)
- [ ] AI analyst format (from home-SOC projects): each alert gets a risk score, confidence
      and MITRE ATT&CK technique, which also teaches the vocabulary real SOCs use

## v2.0

- [ ] Attack lab: deliberately vulnerable practice machines in VirtualBox on an
      isolated virtual network; run real attack tools and watch Matrix detect them
- [ ] Standalone app: installs like any Windows program, no Python needed
- [ ] Router integration: every device's traffic, if the router allows it
- [ ] Always-on sensor: a Raspberry Pi running NetAlertX (or Matrix's own scanner) that
      watches the network while the laptop sleeps and feeds Matrix
- [ ] Blue-team side of the attack lab: Wazuh on a lab VM, with Matrix's AI explaining its alerts
- [ ] Optional Claude for hard questions in Ask Matrix, alongside the local model

## Shipped

- 0.11.3: Fixed a bug shipped in 0.11.2 that froze the whole dashboard (Advisor,
  system meters, device count, version, all stuck on their first paint) whenever
  Living Look was on -- a `ReferenceError` in `livingCore.js` thrown on every
  update. See "Shipped in 0.11.3" above.

- 0.11.2: Away from home -- Matrix now recognizes its home router (learned from
  "Trust all current devices") and automatically stops reading/listing/flagging
  other devices on any other network, plus a manual "Pause device scanning
  right now" toggle in Settings. Also swept out leftover pre-mockup teal-green
  styling everywhere it was hiding, including the app's own icon files (the
  source of the green window title bar/icon), and gave the Network map a real
  makeover -- curved satellite-style connectors, a spinning orbit ring per
  device, and the same translucent "no boxes" backdrop as the rest of the app
  instead of a boxed grid -- plus themed scrollbars app-wide, and (after a design
  review on a mockup canvas) type-tinted glass device nodes with a color legend,
  replacing flat black circles, and a clearer "PHN" phone glyph. See "Shipped in
  0.11.2" above.

- 0.11.1: Living Look rebuilt to actually match design/matrix-living-core.html -- a real
  canvas particle-sphere core with six satellite nodes, a full-page flowing/circuit-trace
  background, and the navy/cyan/gold "no boxes" look applied app-wide, not just Overview.
  See the "Shipped in 0.11.1" section above for the full list and what changed from
  0.11.0's first attempt.

- 0.11.0: ARGUS & MOMUS personas (original characters) with seeded, deterministic quip
  lines on Advisor cards, the digest and proactive notes; optional browser-based
  read-aloud (Web Speech API, no cloned voice) with an auto-read-critical setting;
  installed NVIDIA driver version surfaced with a monthly check-in reminder. (Its
  Living Look part was superseded by 0.11.1 -- see above.)

- 0.10.0: Tune-up 2.0. Less noise: preinstalled extras only shown when they have a
  real cost (disk space, starting with Windows, a second antivirus), ranked by impact.
  "What changed?": a daily settings snapshot (installed/startup apps, running services,
  power plan, Game Mode, Storage Sense) diffed against the day before, with an
  effect note when memory use moved a lot around the same time as a new install.
  Weekly AI digest on the Overview (free, local model), with a "Generate now" button.
  Battery vs. plugged-in power settings side by side (screen/sleep timeout, max
  processor state), "maxed out on battery" flag, battery health (design vs. current
  capacity, cycle count) from Windows' battery report, and a weekly GPU-mode (Eco)
  reminder while unplugged. Modes: one-click Game / Homework / Battery switches you
  configure yourself (power plan, Game Mode, apps to close/open) -- the first place
  Matrix changes a setting instead of only pointing at it, with a preview before every
  apply and "Back to normal".

- 0.9.0: smarter Advisor (Critical / Needs attention / FYI; only Critical flashes;
  Check again; Got it / Keep as is / Snooze; stale FYI items archive themselves;
  "Set aside" and "Resolved recently" lists), troubleshooting plans with memory
  (detects sfc, DISM and memory-test runs; crashes before your last fix stop
  counting; resolves after 3 quiet days), Defender threat detections, faulting
  module + Windows-helper labels for app crashes, history database (performance
  over 24 h / 7 d / 30 d, device first-seen and usual hours, timeline), Timeline
  view, "Since your last visit" and New badges, tray icon with colour status and
  notifications, proactive AI notes on new alerts, Ask Matrix sees plan progress and
  can offer confirm buttons, Identify this device, screenshot to clipboard, copy
  diagnostics. Fixed: "Guessed" / "Private device" came from makers who keep their
  name off the IEEE list (now "Unlisted"), Access-denied on save, long errors
  overflowing, and read access through DNS rebinding (all requests now check Host)

- 0.8.0: installer and updater, background service, own app window, auto-start,
  data kept outside the program folder, side menu with seven views, crash and
  event reporting, tune-up, trust-all and ignore for household devices,
  fix buttons that open Windows pages, chat keeps your question in view
- 0.6: Ask Matrix (local AI through Ollama), naming devices in the dashboard
- 0.4: live PC vitals, Windows health checks, Advisor, device identification
- 0.3: live mode reading the real network
- 0.2: alert explanations, training scenarios
- 0.1: first network map
