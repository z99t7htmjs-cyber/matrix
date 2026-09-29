# Matrix: handoff for a new session (Sep 29, 2026)

Read this first, then ROADMAP.md and README.md.

## The user
- Rob. Windows laptop: ASUS ROG Strix, GeForce RTX 5070, 8 GB VRAM. Not a programmer.
  Wants plain-language explanations and a real program, not a web page he has to run.
- Keep usage lean: short replies, few test renders, no unrequested mockups or options.
- Standing rule: collect bugs and requests into the next batch unless Rob says "fix now".
- Only his real machine and network. No simulations or scenarios in the app.
- Wants information that updates and stays relevant. Old items must resolve or archive
  themselves, not nag. Not everything needs to be live.
- Data safety: nothing leaves the PC unless it's opt-in, labeled, and shows what it sends.
- **IP boundary (firm, tested and held once already):** Rob asked, in an earlier session,
  to clone JARVIS's voice/attitude and use "Ultron" for a future feature, and for
  Iron Man/Ultron easter eggs. That was declined -- no Marvel/Disney names, voices,
  personalities or likenesses in this app, reworded or not, even for personal single-user
  use. What shipped instead is two **original** characters, ARGUS and MOMUS (real Greek
  mythology names, not licensed fiction -- Rob specifically wanted real proper nouns, not
  invented adjective-names like earlier rejected drafts "STEWARD/SPITE" or "NOTED/PETTY").
  Hold this line the same way if it comes up again.
- **No-autonomy rule (firm, explicitly reaffirmed by Rob):** the AI can recommend, rank,
  and narrate as aggressively as it wants, but it never executes a system change on its
  own. Every fix goes through the same preview → confirm pattern Modes established in
  0.10. "Give the AI more hands in things" means better recommendations and louder
  notice, never auto-apply.

## Where things stand
- 0.11.15 is delivered: Matrix now has a real home on GitHub --
  **github.com/z99t7htmjs-cyber/matrix** (public repo; connect a GitHub
  account under claude.ai Settings -> Connectors, then `add_repo` with
  owner `z99t7htmjs-cyber`, repo `matrix`, access `push` to work with it
  from a session). Rob asked to streamline updates; walked him through the
  hosting-vs-automation tradeoff before building anything, landed on
  GitHub-hosted + notify-only (not self-installing), matching Matrix's
  whole "recommend, don't auto-act" character.
  - Hit two real platform limits doing this and want the next session to
    know about them rather than re-discover them: **creating a GitHub
    Release is blocked for this session type** (clean 403), and **so is
    pushing a plain git tag** (also 403). Don't try either again expecting
    a different result -- the update-check was redesigned around neither,
    reading `server/paths.py`'s VERSION string straight off the `main`
    branch via GitHub's public contents API instead (no release, no tag,
    no login). Verified this works fully unauthenticated against the real
    repo before writing the monitor.
  - New `server/update_check.py` (`UpdateCheckMonitor`, checked every 6h)
    feeds a normal Advisor card when a newer version exists. Deliberately
    NOT included in `Monitor.warmed_up()`'s gate (the fix from
    0.11.13/0.11.14) -- it depends on internet/GitHub reachability, which
    can genuinely never succeed on a locked-down network, so gating every
    other alert's resolution on it would be strictly worse than the small
    risk being excluded actually carries. Reasoning is in the docstring;
    don't "fix" this by adding it to the gate without re-reading why.
  - **Not built:** an actual one-click "apply the update" action (Matrix
    downloading and running the installer itself). Told Rob plainly this
    is separate, bigger work and it hasn't been started -- the repo and
    the notify-only check are the whole of what's live.
  See ROADMAP.md's "Shipped in 0.11.15" for what was verified and how.
- 0.11.14 is delivered: Rob installed 0.11.13 and said the items came back
  again anyway. Didn't assume the fix was already right -- went looking for
  what it missed, and found a real second gap: 0.11.13's `warmed_up()` only
  covered the five `PeriodicMonitor`-based checks. Network (`NetworkBuilder`,
  its own loop, its own first-build delay) and system vitals (a short but
  real gap before `SystemMonitor`'s first sample) aren't `PeriodicMonitor`s
  and weren't covered at all -- so a snoozed "unknown device" alert was
  exactly as exposed to the same startup-race false-resolve as the Tune-up
  items 0.11.13 actually fixed. Reproduced this one specifically (a snoozed,
  not just kept, network alert) against the real `AlertManager`/`History`
  before and after the fix. **Told Rob directly, unprompted:** this only
  stops it going forward -- anything already reset to "New" by the bug
  before 0.11.14 stays that way once, and the real test is whether it
  recurs on a restart *after* this version, not whether it still looks New
  immediately after updating to it. See ROADMAP.md's "Shipped in 0.11.14".
  **Did the full structural audit in the same session rather than leaving
  it as a "check this later":** grepped every `state["..."]`/`state.get(...)`
  read across all 15 `advisor.py` rule functions and cross-checked each one
  against `Monitor.warmed_up()`. Every source that feeds a non-transient
  suggestion is now covered (health, events, tuneup, drives, thermal,
  network, system) except one, and that one is safe by design, not by
  oversight: `meta.vendorDb` (the manufacturer-lookup status) starts at
  `"loading"` and moves exactly once, permanently, to `"ready"` or
  `"unavailable"` (`identify.py`'s `VendorDB._load()`) -- it can't flicker
  present/absent the way a still-loading check's data can, so there's no
  window for this same bug to hide in there. If a *third* instance of this
  pattern turns up, it means either a new background source was added
  without updating `warmed_up()` to match, or a genuinely different bug --
  re-run this same grep-and-cross-check first before assuming it's the
  latter.
- 0.11.13 is delivered: Rob flagged, from a screenshot, that Advisor items
  "pop up with every new edition regardless if i have muted or ignored
  them." Found a real bug and fixed it, reproduced before and after: several
  background checks (Tune-up especially) can take up to a minute to report
  after Matrix starts, and Matrix restarting is exactly what a new edition
  does. `alerts.py` marks an item "resolved" after just 20 seconds of being
  absent from the Advisor's suggestions (2 evaluation cycles, 10s apart) --
  so during that startup window, a kept/snoozed item whose check hadn't
  reported yet looked "resolved," then got reborn as brand-new the moment
  the real check caught up, discarding the decision. This is likely the real
  explanation for the "keeps repeating" pattern flagged back in 0.11.10,
  which that session's `alerts.py` review didn't catch because the race
  wasn't happening in the moment it was tested. Fixed by having `Monitor`
  track whether every check has completed its first real read since startup
  (`warmed_up()`); `alerts.py` won't treat anything as resolved until then.
  Also added Windows Update failure detection (via the Update Agent's own
  history, `Microsoft.Update.Session` -- unelevated, well-documented), since
  the existing "days since last update" only ever looks at *successful*
  installs and can't tell a PC that's current apart from one silently
  failing every attempt. Talked through the other three efficiency-report
  options (CPU temp, backup status, BIOS tracking) with Rob rather than
  building any of them blind -- CPU temp specifically would mean giving
  Matrix (or a helper process) admin rights it doesn't currently need for
  anything, a real architecture tradeoff, not a free add; tabled, not built.
  See ROADMAP.md's "Shipped in 0.11.13" for what was/wasn't verified.
- 0.11.12 is delivered: Rob asked for a fresh-eyes efficiency review of the
  whole app (what's missing, what's wasted, how to best run/maintain the
  laptop long-term) -- explicitly *not* "cut things to save resources."
  Delegated the factual research (what Windows APIs exist for drive
  health/thermal data, what other monitoring tools typically cover) to a
  sub-agent, then did the actual analysis and report myself, then used
  `AskUserQuestion` to let Rob pick priorities directly rather than guessing.
  He picked: new coverage = drive health (SMART) + a fan/dust proxy;
  cleanup = fix the GPU-mode nag repeating every week, drop Windows-health
  fields that were collected but never read anywhere, and slow down two
  background checks that were running far more often than their data
  actually changes. Built all of it -- see ROADMAP.md's "Shipped in 0.11.12"
  for the full list and what was/wasn't verified. Both new checks are
  read-only, like everything else in this app, and both new Tune-up cards
  show a plain "here's the current state" confirmation rather than only
  ever speaking up when something's wrong, matching what Rob specifically
  pushed for earlier in the battery-warning and GPU-mode-nag feedback.
- 0.11.11 is delivered: Rob's next recording still showed a jump after
  0.11.8's timing fix, and this time it was a genuinely different, second
  bug, found by measurement rather than more guessing. Wrapped
  `Math.random()` with a counter and watched it live: ~15,324 calls, every
  single poll cycle (every 3s), forever -- a full rebuild of all 3,200
  Living Look particles, on a fixed 3-second cadence with nothing to do with
  the animation's own frame rate. Cause: Overview's full-HTML-rebuild-per-
  poll architecture means `#living-core-mount` is a fresh DOM node every
  poll, so `mount()` re-parents the persistent canvas into it every time --
  and `_resize()`, called unconditionally on every re-parent, rebuilt the
  entire particle field regardless of whether the canvas had actually
  changed size. Fixed by making `_resize()` a no-op when the dimensions
  haven't changed. Verified with the same counter: 0 rebuild calls across
  two full poll cycles after the fix. Also added scrollbar auto-hide (it
  was permanently visible before, a real but different thing from what Rob
  wanted) -- `body.is-scrolling` toggles on scroll (capture-phase listener,
  since `scroll` doesn't bubble) and clears ~900ms after the last scroll
  event; the themed scrollbar thumb fades in only while that class is set.
  Verified headlessly. See ROADMAP.md's "Shipped in 0.11.11".
- 0.11.10 is delivered: Rob said the "processor can run at full power on
  battery" warning keeps showing up, but his Windows power plan shows as
  "Balanced." Checked the collector (`tuneup.py`) -- it correctly queries
  `SCHEME_CURRENT` (the active plan, not a hardcoded one), so no bug found
  there. Most likely explanation: it's checking a real but *different*
  setting than the plan name -- "Maximum processor state" is a separate,
  deeper control under Advanced power settings that Windows can leave at
  100% even on "Balanced." Made the warning say the exact plan name and the
  exact deeper setting/path so this is directly checkable instead of vague.
  Also went hunting for a "keeps repeating" bug in `alerts.py`'s lifecycle
  and couldn't find one -- an unchanged active item shouldn't re-raise or
  re-tag "New" as written. Documented an honest best-guess (Armoury Crate
  itself may be flipping the real Windows setting when it switches power
  modes) rather than inventing a fix for a bug that isn't there. See
  ROADMAP.md's "Shipped in 0.11.10" -- flag it if Snooze/Keep as is don't
  actually stop the nagging, since that would be a separate, real bug.
- 0.11.9 is delivered: Rob asked about MOMUS (the original Ultron-stand-in
  persona -- see the IP boundary note below) not having any presence. He was
  right: `persona.py`'s own docstring promised him "a rare swap-in
  elsewhere" beyond critical items, but that was never actually built --
  every non-critical branch hardcoded ARGUS, and MOMUS only had 4 total
  lines in the whole app, reachable 35% of the time on critical items only
  (rare for a typical home setup). Gave him real `new`/`snoozed_repeat`/
  `still_open` banks in his own distinct voice, wired him into every bucket
  at a real (lower than critical) rate via `MOMUS_CHANCE`, and kept the quip
  badge and the AI-note voice picker sharing the same seeded selection so
  they can't disagree about who's speaking. Verified deterministically
  (rate, distinct lines, zero badge/AI-note mismatches across 200 synthetic
  items). Same caveat as before: can't verify his AI-*written* paragraphs
  actually sound different without Rob's real local model running. See
  ROADMAP.md's "Shipped in 0.11.9".
- 0.11.8 is delivered: found the actual cause of the animation looking slow
  and jumpy -- it was never unfocused-window throttling (that fix was real
  but not the cause). `livingCore.js` and `livingBackground.js`'s `_loop()`
  was setting `this.last = now` to the current frame's own timestamp right
  before `_frame()` diffed a fresh `performance.now()` against it, so `dt`
  came out essentially zero every frame, forever -- proved with a plain-JS
  simulation outside the browser (5 simulated seconds of frames produced a
  clock that advanced by 0.0000). Fixed by removing that line; `_frame()`
  already updates `this.last` correctly on its own. Verified by pixel-sampling
  the real canvas over time and confirming it now changes meaningfully every
  half-second instead of sitting nearly static. Also fixed ARGUS's "new item"
  quip bank in `persona.py`, which was the one card state with zero
  personality (bare "New: {title}." templates) while every other bank had
  real wit -- and it's the bank almost every card actually hits. Verified
  deterministically. Separately, strengthened (but could not independently
  verify, since this sandbox can't run Rob's local Ollama model) the wording
  sent to the AI for the longer "ARGUS SAYS" notes, since two "be plain"
  rules were competing with the persona instruction. See ROADMAP.md's
  "Shipped in 0.11.8".
- 0.11.7 is delivered: 0.11.6 fixed the connection-refused freeze, but Rob's
  next recording showed a second, different cause of the same "stuck on
  Waiting for Matrix..." symptom, this time only at startup. Root cause:
  `system.py`'s vitals sampler reports `available: true` as soon as psutil
  imports, before its first background sample actually completes a couple
  seconds later (or forever, if sampling keeps failing) -- so there's a real
  window where `available` is true but `system.cpu` etc. don't exist yet.
  The front end's `renderMeters()` assumed otherwise and threw reading
  `system.cpu.usage`, and because the poll loop in `dataService.js` only
  scheduled its next fetch *after* calling every listener, that one throw
  silently killed polling forever -- not just that one frame. Reproduced
  headlessly first (confirmed the exact JS error and permanent freeze), then
  fixed both the immediate cause (`renderMeters()` now reads every field
  defensively) and the underlying fragility (`dataService.js` now wraps each
  listener call in try/catch, so a future rendering bug can't cause this same
  permanent-freeze pattern again). Verified the fix recovers correctly with
  the same headless repro. See ROADMAP.md's "Shipped in 0.11.7".
- 0.11.6 is delivered: found and fixed the real cause of the whole evening's
  "dashboard won't populate" saga (no version, no CPU/GPU/network data,
  stuck on "Waiting for Matrix..."). It was never the animation, a stale
  window, a zombie process, or the Jetwriter extension -- all ruled out one
  at a time on Rob's own evidence first. The actual cause: `matrix_server.py`
  was using Python's default `listen()` backlog of only 5 pending
  connections, but the dashboard's first load fires off ~30 requests at
  once; past 5, the OS silently refuses the rest (`ERR_CONNECTION_REFUSED`,
  confirmed in Rob's own Network tab screenshot -- 14 of ~30 requests
  refused). Because `app.js` statically imports every view module together,
  even one refused script file breaks the entire import and means *none* of
  app.js's code runs -- not the state poller, nothing -- which is exactly
  the "frozen on first paint, no JS errors from Matrix's own code" symptom
  Rob saw. Fixed with a `Server(ThreadingHTTPServer)` subclass setting
  `request_queue_size = 128` as a *class* attribute (has to be set before
  construction -- caught and corrected my own first attempt, which set it as
  an instance attribute too late to matter, by reading Python's
  `socketserver` source). Verified via full JS/Python compile checks and a
  real-data regression re-run; **not** verified via an end-to-end load test
  that reproduces the refusal (a synthetic 30-at-once test didn't reliably
  reproduce it in this sandbox's faster thread scheduling), so if Rob still
  sees `ERR_CONNECTION_REFUSED` in Network on 0.11.6, there's a second
  factor and this isn't the whole story. Also removed a wasteful per-poll
  rebuild of the Living Look's background particles, and raised the
  animation `dt` clamp in both `livingCore.js` and `livingBackground.js` so
  an unfocused-but-visible window doesn't render in visible slow motion. See
  ROADMAP.md's "Shipped in 0.11.6" for the full writeup, including two still-open
  items (Stop Matrix button, background line smoothness).
- 0.11.5 is delivered: fixed a real, headless-confirmed scroll jump on Overview
  (scroll position was restored *before* the Living Look scene remounted into
  its placeholder div each poll, so the page grew underneath the scroll a
  moment later and Chrome's scroll-anchoring yanked the viewport). Rob's
  specific report ("click the down arrow, stop, jumps to top") wasn't
  reproduced exactly -- only a jump-down was -- so treat this as a real fix to
  a real bug in the same area, not a confirmed closure of his exact symptom
  until he says so. He may also still have been on 0.11.3 when he recorded it
  (the native scrollbar arrow button 0.11.4 removes was still visible in his
  video), so double check which build he's actually on before digging further.
  See ROADMAP.md's "Shipped in 0.11.5".
- 0.11.4 is delivered: fixed the themed scrollbar's leftover OS-gray arrow
  buttons (looked "glitchy" next to the cyan thumb) and the satellite
  connector dots' visible loop-reset snap (see ROADMAP.md's "Shipped in
  0.11.4"). Also ruled out Matrix's own code as the source of the still-green
  title bar Rob keeps seeing -- every asset (theme-color, manifest, icons) is
  confirmed navy/cyan, and `desktop.py` never touches window/caption color, so
  this now points at Windows' own "accent color on title bars" setting rather
  than anything in the app. **Not yet confirmed by Rob**, on any of the three.
- 0.11.3 is delivered, and it's a "fix what I just broke" release: 0.11.2 shipped with
  a real bug (a `ReferenceError` in `livingCore.js`, see ROADMAP.md's "Shipped in 0.11.3"
  for the exact cause) that froze the entire dashboard -- Advisor, system meters, device
  count, version, all stuck on their first paint, forever -- for anyone with Living Look
  on (the default), which is everyone who hadn't turned it off. Rob caught it because he
  installed 0.11.2 and the app looked completely dead; he pasted the in-app "Copy
  diagnostics" output, which showed the *server* was working fine the whole time (fresh
  background-check timestamps, real CPU/GPU/network data) -- that's what pointed at a
  front-end rendering crash rather than a backend problem. **Lesson for next time:**
  every headless-browser check this session had run against Overview either had Living
  Look off, or didn't check for console/page errors, or checked errors on a different
  view -- so a crash that only fires on "Overview + Living Look on + not away" slipped
  through every test. The fix (`/tmp/claude-0/.../scratchpad/overview_crash_check.py`,
  not shipped, but worth recreating as a habit) checks all three Overview states
  (Living Look on/off, away/not-away) for *any* JS console error, not just whether a
  screenshot looks right. Do this for any future change to `livingCore.js`, `app.js`'s
  `onState`/`renderView`, or anything else in that per-poll render path -- a crash there
  silently freezes the entire dashboard, not just one section, and a screenshot taken
  seconds after page load can look completely fine even while every subsequent poll is
  throwing, because whatever painted before the crash line stays on screen.
- 0.11.2 (before the bug above was found) added: Rob reported that on his school's wifi, Matrix was still listing and
  flagging other devices -- it felt like it was watching a network it had no business
  watching. The scan was already passive (`arp_neighbors()` only reads the OS's own ARP
  cache; it never pings or probes anyone else), but the dashboard didn't know or say that
  it was somewhere unfamiliar. 0.11.2 adds an automatic fix ("Trust all current devices"
  now also remembers the home router's MAC, so Matrix recognizes any other network and
  quietly stops reading/listing/flagging other devices on it -- no toggle needed) plus a
  manual "Pause device scanning right now" toggle in Settings for immediate/forced use.
  The Network view, Overview's network card, and the Living Look's network satellite all
  say plainly when this is active, instead of just showing a sparse device list.
  Separately, Rob spotted a green bar at the top of the Network map -- turned out the
  map's grid background and scan-line sweep, plus a few other spots (sparkline fills,
  chat bubbles, active tabs, table-row hover), were still using the old pre-mockup
  teal-green (#36e2b4) that never got swept when the palette moved to navy/cyan. All of
  it is now consistent, and the map itself dropped its boxed-grid look for the same
  translucent "no boxes" backdrop the rest of the app uses.
- The real source of the green title bar/window icon turned out to be the app's own
  icon files -- `icons/matrix-192.png`, `matrix-512.png` and `matrix.ico` were still the
  old teal-green "M" mark from before the palette rewrite (Chrome's `--app=` window uses
  these for its title bar icon). Recolored via a masked HSV hue-rotation
  (`/tmp/recolor_icons.py`-style script, teal ~165° -> accent cyan ~196°) so the shading
  and anti-aliasing survived the swap. Rob also asked for the Network map's connections
  to feel more "futuristic": straight `<line>` connectors became soft S-curve `<path>`s
  (same style as the Living Look's satellite links), each row now sits on a shallow arc
  instead of a flat line, and every device got a slow-spinning dashed orbit ring. Also
  added themed (thin, accent-colored) scrollbars app-wide, replacing the OS default.
- The flat black device circles got a real design pass: I mocked up three directions
  (gradient orb, type-tinted glass, vivid filled) on a design canvas so Rob could
  compare them side by side rather than guess from a description, and he picked
  type-tinted glass. Implemented in `js/data/deviceTypes.js` (`color` per type) and
  `js/components/networkMap.js`/`css/styles.css` (`--type-color` custom property set
  per node in JS, so offline/threat states cleanly override the type color without
  fighting CSS specificity). Also renamed the phone glyph "MOB" -> "PHN" (was easy to
  misread) and added a color-key legend under the map.
  See ROADMAP.md's "Shipped in 0.11.2" section for the full list.
- 0.11.1 is delivered. 0.11.0 shipped ARGUS & MOMUS + driver visibility + a first pass at
  Living Look; that first pass was built from the roadmap's *text description* of the
  Living Look instead of the actual reference file already in the project,
  `design/matrix-living-core.html` -- a fully-built concept page, not a sketch. Rob
  caught this immediately ("this doesn't look like the mockup we agreed on") and 0.11.1
  replaces that first attempt with a real port of the mockup's canvas engine (rotating
  particle sphere, satellite nodes, flowing circuit-trace background) wired to live data,
  plus its navy/cyan/gold "no boxes" look applied to the whole app, not just Overview.
- **Lesson for next time:** when a roadmap item references a concept page, mockup, or
  design file by name, open and actually match that file before building -- a roadmap's
  prose description of a design is not the design. `design/matrix-living-core.html` is
  now the standard for Matrix's look; anything that changes the visual direction again
  should update that file (or a successor) rather than just the roadmap text.
- See README.md and ROADMAP.md's "Shipped in 0.11.1" section for the full list of what's
  in it, including the two small things intentionally left out (a live events feed and a
  red-alert banner overlay, both in the mockup but judged redundant with the existing
  Advisor panel/Timeline for this pass).
- Two things from 0.10 were intentionally left out (no reliable way to do them yet):
  Do Not Disturb for Modes, and switching Armoury Crate's Silent/Performance/Turbo
  from Matrix. Don't attempt these unless a real API turns up; say so if Rob asks.
- v2.0 (much later): attack lab (VMs), standalone app, router, Raspberry Pi sensor, Wazuh.

## How it's built (short)
- Python standard-library server on 127.0.0.1:8080 (server/matrix_server.py) with read-only
  collectors (PowerShell, arp, netstat, psutil, nvidia-smi, powercfg), history in SQLite,
  local AI via Ollama (qwen3:8b), tray icon via ctypes.
- Front end: vanilla ES modules, CSS variables, hash router.
- Modes (server/modes.py) is the one place Matrix changes a Windows setting instead of
  only pointing at it (power plan, Game Mode, closing/opening apps you configured) --
  keep that exception narrow and always preview before applying.
- Data dir %LOCALAPPDATA%\Matrix, program dir %LOCALAPPDATA%\Programs\Matrix.
- Install or update: unzip (Extract All first), then double-click "Install or Update Matrix".
- Bump VERSION in server/paths.py for each batch. Test with fake Windows data on Linux in a
  headless browser before delivering. Things that only run on Windows (tray, screenshot,
  CBS/DISM logs, Defender, powercfg, registry writes) can only be tested with fake data --
  write a small throwaway script that feeds fake PowerShell-shaped JSON into the parse_*
  functions rather than trusting the real collectors, and delete it before delivering.

## Delivering a batch
Zip the project as Matrix-<version>.zip, send it, and tell Rob: Extract All, then run
"Install or Update Matrix". His data is kept.
