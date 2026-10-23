# Limitless Sound: handoff for Claude Code

**Bennet:** open Claude Code in a folder on your Mac and paste this whole file in, or say
"Read HANDOFF-CLAUDE-CODE.md in github.com/chittychitty38/Limitless-sound and pick up the project."
Written 2026-10-23, after the 0.2.4 release. Everything below is the state of the project then.

---

## Instructions for Claude Code

You are picking up **Limitless Sound**, a suite of free, offline, accessible music apps for
musicians with disabilities. Bennet (GitHub `chittychitty38`) leads it. Until now the work was
done by Claude in cloud sessions that could not touch a real Mac, mic, webcam, controller or DAW.
You can. Your main value is proving and fixing the apps on real hardware.

Start by doing this, in order:

1. Clone the repo and read the files named in "Where things live".
   `gh repo clone chittychitty38/Limitless-sound LimitlessSound && cd LimitlessSound`
   (install `gh`, `python@3.12`, `node@22`, `rustup-init` with Homebrew first if missing).
2. Ask Bennet, in one message, which Mac he is on (Apple silicon or Intel, macOS version),
   which DAWs he has (Logic Pro, Pro Tools, Ableton) and which hardware is with him today
   (mic, webcam, Xbox Adaptive Controller, switches, foot pedal, Line 6 Helix).
3. Show him the "Open items" list below and ask which one to do first. If he has no
   preference, start with the hands-on Mac test (item 1).

How to work with Bennet:
- He is the musician and tester, not a developer in this session. Explain in plain words,
  ask for one physical action at a time, and wait for his answer.
- Never change his system settings yourself. Tell him where to click.
- His bar: every tool must be **real, installable software** that works on virtually any Mac
  or Windows PC with an ordinary mic and webcam, with "incredible starting results" out of the
  box. Not dev prototypes, no shortcuts. Mac first.
- Pushing branches, opening PRs and merging green PRs to `main` is approved ("Full send").
  Ask before anything outside the repo (emails, public posts, paid services, signing certs),
  and before deleting branches or releases.
- Polished deliverables for people outside the project should be beautiful PDFs, in the
  Limitless Sound Foundation branding (below).

---

## Mission

"Music is for every body." Build software so musicians with disabilities can make music and
use technology. No one left behind. The project is tied to the **Limitless Sound Foundation**,
a 501(c)(3) in Conyers, Georgia, founded by Jason Barnes (a drummer with a prosthetic arm).

## The suite

One repo, a monorepo: **https://github.com/chittychitty38/Limitless-sound** (public).

| App | Folder | What it does | Stack | Released |
|---|---|---|---|---|
| Limitless Sound | `shared/hub` | Joins the apps into one suite (any input can trigger any app); the guided setup, shared settings and language | Python stdlib only | 0.2.3, in the suite |
| Limitless Voice | `apps/voice` | Offline voice commands for Logic, Pro Tools, Ableton Live and the computer | Python 3.12, PySide6, Vosk 0.3.44, PyInstaller | voice-v0.3.9 |
| Limitless One-Hand | `apps/one-hand` | Keys under one hand become DAW commands; hold Space to mirror-type | Python, PySide6, Quartz event tap / Win hook | one-hand-v0.2.4 |
| Limitless Zoom | `apps/zoom` | Zoom the DAW or screen by voice, one hand, dwell or a switch | Python, PySide6, pynput, Vosk | zoom-v0.1.4 |
| Limitless Color | `apps/color` | Recolors the whole screen for colorblind musicians | Rust, Tauri 2, Swift ScreenCaptureKit + Metal overlay | color-v0.1.4 |
| Limitless Control | `apps/control` | Xbox Adaptive Controller, switches, gamepads as DAW keys | Python, pygame-ce (SDL2), local web settings page | control-v0.2.6 |
| GazeStage | `apps/gazestage` | Play instruments and run the transport with eyes, head, a sound or a switch | Electron 39, MediaPipe face landmarks in a worker, built-in instrument in a hidden page of its own, virtual MIDI ports, XY tone pad | gazestage-v0.4.3 |
| **Suite** | `packaging/` | One download with everything: a standard Mac installer (`.pkg`) and a Windows installer (`.exe`) | `suite.yml` | **v0.2.4** (the repo's Latest release) |

Every app meets **Limitless Access Standard level 2 (Adaptive)**: it follows the shared text
size, high contrast and reduced motion live and reports `prefs.applied`. Every app keeps a log
file (Limitless Sound's page › Activity › **Open the log folder**).

Every screen works with a screen reader and the keyboard alone, and CI checks it: the web-based
screens (Limitless Sound's page, Control's page, GazeStage, Color, the Mac installer) pass WCAG 2.2
AA in every look with a keyboard walk (`.github/scripts/apps-a11y.cjs`, `screens.yml`, #79), and
the Qt apps have `tests/test_accessibility.py` (#75). Every app presses the same key for the
same thing in the same DAW (`stress/test_daw_keys_agree.py`, #85).

Release links (permanent; they always point at the newest suite):
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-apple-silicon.pkg
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-intel.pkg
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-windows.exe
- All releases, including each app's own: https://github.com/chittychitty38/Limitless-sound/releases

Nothing is signed. macOS needs **System Settings → Privacy & Security → Open Anyway** once,
Windows SmartScreen needs **More info → Run anyway**. Signing needs an Apple Developer ID and a
Windows code-signing certificate, which Bennet doesn't have yet.

### How the hub works
Hub on 127.0.0.1: TCP 47900 (NDJSON, apps connect) and HTTP 47901 (settings page and one-shot
triggers like `/do/daw.record?t=<token>`). Discovery file `link.json` (port + token) in the shared
"Limitless Sound" config folder. Actions are `<tool>.<action>` (voice, onehand, zoom, color,
control, gaze, hub). Intents like `daw.play` go to whichever open app can press DAW keys.
"Sidechain links" are event → action routes (e.g. while recording, Voice only hears stop/wake
words). The first time the settings page opens it runs the **guided setup**: how do you like to
play, how should things look, which language; it opens the apps that fit and sets the shared
settings. The shared `language` ("en" or "es", first set from the computer's own language) is
followed by every app that has it; the page itself is in Spanish too, and the hub reads each
app's replies with a voice for the language that app reports (#83).
Spec: `shared/PROTOCOL.md`. Clients for Python, JavaScript, Rust and C++ (one header, for
plug-in and hardware makers) in `shared/clients`; apps carry copies, which the hub's tests keep
identical. Every app works alone without the hub.

## Where things live

- `README.md`, `CONTRIBUTING.md`: suite overview and per-app conventions.
- `HANDOFF.md`: the hands-on Mac test, step by step, for you to walk Bennet through.
- `apps/<app>/README.md`: each app's details and what has and hasn't been tested.
- `.github/workflows/<app>.yml`: one workflow per app (macos-15, macos-15-intel, windows-latest),
  path-filtered to its folder. `shared.yml` tests and builds the hub and clients. `stress.yml`
  runs the stress tests a change needs (all of them on `main` and nightly). `suite.yml` builds
  the suite installers. `proof.yml` is the nightly proof (below).
- `stress/`: stress tests per app (latency, floods, soaks, focus loss, relaunch).
- `packaging/VERSION`, `packaging/RELEASE.md`: the suite version and its release notes.
  `packaging/mac`, `packaging/windows`: the installers. `packaging/proof`: the proof script.
- `standard/`: Limitless Access Standard draft and its test kit (`standard/conformance/las_check.py`).
- `docs/`: the public website (also copied to the `gh-pages` branch).
- Older prototypes in Bennet's Claude project files (Karabiner one-hand, Hammerspoon zoom,
  AdaptiveMapper Swift, browser color tuner) are superseded by the apps above. Ignore them.

### How releases work
- **An app** releases itself: on a push to `main` with a new version, its workflow publishes
  `<folder>-v<version>` with Mac (Apple silicon + Intel) and Windows builds, not marked Latest.
  To release, bump its version and merge to `main`: Voice `apps/voice/limitless_voice/__init__.py`,
  One-Hand `apps/one-hand/onehand/__init__.py`, Zoom `apps/zoom/limitless_zoom/__init__.py`,
  Control `apps/control/limitless_control/__init__.py` (+ `pyproject.toml`, `installer.iss`),
  Color `apps/color/Cargo.toml` + `app/src-tauri/tauri.conf.json` + `Cargo.lock`, GazeStage
  `apps/gazestage/package.json` + `package-lock.json`, hub `shared/hub/limitless_hub/__init__.py`.
- **The suite** releases when `packaging/VERSION` changes on `main`: `suite.yml` takes every
  app's newest successful `main` build and publishes `v<version>` as the repo's Latest.
- After that, every app build on `main` should refresh the suite's installers by itself (a
  `workflow_run` trigger), but GitHub only runs that, schedules and "Run workflow" buttons for
  workflows on the **default branch**, which is still `zoom-view-control` (open item 3). Until
  it changes, refresh the suite after an app release by merging any change to
  `packaging/RELEASE.md` (a later build of the same suite version replaces its installers).

### Nightly proof
`proof.yml` downloads the **public** suite from the Latest release onto fresh Apple silicon and
Intel Macs and a Windows PC, installs it the way a musician would, opens every app, checks each
joins the suite, presses every action it offers, and measures start time and idle CPU. It prints
each app's log and crash reports in the workflow log. Results go to the `proof-results` branch
and the website's Proof section (`proof-results-test` from a PR). It runs on a pull request that
changes the proof, and nightly (or with "Run workflow") once the default branch is `main` (open
item 3).

Its runs on 0.1.0 to 0.2.1 found every bug fixed in 0.2.0 to 0.2.2: Zoom crashing on Apple
silicon, Control taking 37 s to start, GazeStage leaving actions unanswered on a Mac without
working audio, Zoom's and GazeStage's idle CPU, and false crash logs on Windows. **0.2.4 passes it
on all three computers with nothing left to improve** (run 39900701509, on the website):
- Every app is ready in 0.6–11 s, at Access Standard level 2, with every action answered and no
  timeouts.
- Every suite check is green, including Limitless Sound's own page opening (S4, #86).
- Every app is at or under 1.1% of the CPU sitting idle: Control 1.1% on the Intel Mac, down
  from 2.8% in 0.2.2; GazeStage 0.3–0.7%.
- The installer takes 7 s on Apple silicon, 14 s on Intel and 63 s on Windows.

An app over the limit names its busiest processes (#62). To run it again before the default
branch is `main`, open a PR that touches `packaging/proof/`, then publish its results: point the
`proof-results` branch at a commit with the tree of `proof-results-test` (`git commit-tree`), and
copy its `latest.json` to `proof/latest.json` on `gh-pages`.

## Public website and branding

- Live: **https://chittychitty38.github.io/Limitless-sound/** (capital L; always share that one).
- Source: `docs/index.html` on `main`. GitHub Pages serves the `gh-pages` branch, a flat copy of
  `docs/`. After changing `docs/`, copy it to `gh-pages` and push, or ask Bennet to switch Pages
  to "main /docs" in repo settings so it updates by itself.
- Each app's Download link finds that app's newest release by itself (GitHub's API, in the page);
  the version written in the page is only the fallback.
- In Spanish at `/es/` (`docs/es/index.html`), linked both ways. Copy `docs/es/` to `gh-pages`
  too. The site check fails if its styles drift from the English page's or English is left on it.
- Branding (Bennet: "lock it in"): night navy `#13121f`, cream `#f3eee4`, crimson pill buttons
  `#d2334c`, lavender italic accent `#b4b0fa` (Instrument Serif), Bricolage Grotesque headings,
  JetBrains Mono uppercase tracked labels, Atkinson Hyperlegible body, the LAS heart logo
  (`docs/logo.png`). Use it for every Limitless Sound deliverable. Bennet's own preview site:
  https://limitlesssoundpreview.netlify.app/

## The bigger vision

- **38x plan** (`docs/Limitless-Sound-38x-Plan.pdf`, also on the site), from Bennet's voice memo:
  regular interviews and outreach with disabled musicians; a "Pimp My Ride" pilot where sponsors
  pay to kit out 1-2 artists (first: Jason Becker, via Kiesel, who make his signature guitar);
  a guest-feature song series with Panda Studios (e.g. Andrew from The Ghost Inside, a guitarist
  who plays with his feet) with sponsors like Marshall, DW, Line 6; an XY tone pad Jason Becker
  can play; and an open accessibility protocol "like MIDI".
- **Limitless Access Standard** (`standard/`): levels and a test kit built on the hub protocol.
  All six apps meet level 2. The C++ client makes it practical for plug-in, amp-modeler and
  hardware makers (JUCE, iPlug2, VST3, AU, CLAP) to carry the mark.
- **Heartmark concept 0.2** (Sam's idea; PDF in Bennet's project files,
  `vision/heartmark/Limitless-Heartmark-Concept.pdf`): the Heartmark as the compliance mark,
  "Made for Any Body" as the box line, a hardware track, six pillars (Reach, Connect, Sense,
  Adapt, Endure, Explain), the four levels, and a Limitless Builders program. Open calls for
  Bennet and Sam: final names, fund percentage (10% proposed), who holds the mark (nonprofit?),
  first partner (Line 6 or Kiesel).

## What has never been proven

Every app builds, installs and passes its automated and stress tests on GitHub's machines, and
the nightly proof installs the public download on fresh Macs and Windows and drives every app.
Those machines have no screen, mic, camera, controller, DAW or privacy permissions, so:
- No app has run on Bennet's Mac with his real mic, webcam, controller and DAW.
- Color's Mac overlay has never drawn on a real screen.
- Control has never seen a real Xbox Adaptive Controller.
- One-Hand's Mac self-test passes even if the key hook can't start; check it really types.
- GazeStage has never driven a real Pro Tools rig (HUI ports, rewind/ffwd/stop mapping).
- Voice and Zoom are measured against recordings of real people, in CI (`stress/README.md`,
  "Real people"): about 200 people saying single words (Speech Commands), people saying the DAW
  command words themselves ("cut", "record", "solo"; MLCommons' Multilingual Spoken Words, #77),
  and an hour of 40 people reading aloud (LibriSpeech). Nobody has spoken to them in a real room
  with a real DAW running.
- Nobody who speaks Spanish has used the Spanish Voice or read the Spanish page (#83).
- No DAW key has been pressed in a real DAW. The keys come from the vendors' guides, and every
  app agrees with every other (`stress/test_daw_keys_agree.py`).
- The C++ client has only been tested against the hub, not inside a real plug-in host.
- No musician with a disability has tried any of it yet.

## Open items

1. **Hands-on Mac test.** Follow `HANDOFF.md`. It walks Bennet through installing the suite,
   the guided setup, running the stress tests on the real Mac, and checking each app by hand,
   recording results in `HANDOFF-RESULTS.md`. Fix what fails, one PR per app, and release
   fixes by bumping versions.
2. **The tone pad with a real Helix.** GazeStage 0.4.1 has the tone pad (#21, #67), the XY
   controller from Bennet's Jason Becker / Line 6 Helix idea: two CCs (default 16/17; the Helix
   profile sends CC1/CC2 = EXP1/EXP2) to a USB Line 6 device if one is plugged in, else to
   "GazeStage Notes". Other apps move it with GazeStage's actions `xySet`, `xySnapA`–`D`,
   `xyCenter`, `xyLeft`… (0.4.2, #70). **Untested with real Line 6
   hardware**; `HANDOFF.md` has the steps. The CC1/2 mapping comes from Line 6's MIDI table.
3. **Default branch → `main`.** The repo's default branch is still `zoom-view-control`. Ask
   Bennet to change it at **GitHub › the repo › Settings › General › Default branch** (or run
   `gh repo edit chittychitty38/Limitless-sound --default-branch main` with his OK). Until then
   the nightly proof and nightly stress runs don't run, no workflow can be started by hand, and the
   suite installers aren't refreshed after an app release (see "How releases work").
4. **Signing.** Apple Developer ID ($99/year) for a signed, notarized `.pkg`, and a Windows
   certificate for the installers. Bennet's decision; once he has them, add them as repo secrets.
   Voice's workflow already signs and notarizes when the `APPLE_*` secrets exist; the other
   apps and the suite `.pkg` need the same steps added.
5. **Clean up stale branches** (many old `claude/*`, `suite/*` and app branches whose PRs are
   merged, and the throwaway `diag/control-startup`, `diag/control-idle`, `diag/gazestage-idle`
   and `diag/zoom-idle`).
   Ask Bennet first; cloud sessions weren't allowed to delete them.
6. **Voice: stray single words.** On real people's recordings (`stress/test_voice_real_speech.py`,
   `stress/test_command_words.py`, each run prints these):
   - Voice hears 91% of the words it listens for, and 73% of real people's DAW command words at
     once, 82% at once or after "Say yes to cut, or cancel" (0.3.8).
   - It never pressed Cut, Paste or Delete for a word that wasn't one.
   - In an hour of people reading aloud it fired 0 commands with Logic in front and 3.8 with
     Pro Tools, none destructive.
   - Stray single words that aren't commands still fire a harmless one 17.8% of the time ("happy"
     → Copy, "wow" → louder, "follow" → Solo, "bird" → Record). Requiring both listeners to agree
     on every one-word command would cut that to 1.3% but takes command words from 73% to 47% right
     ("undo" 85% → 6%), so it isn't done. A better command model (item 7) is the likelier fix.
7. **A better speech model for Voice's commands: Bennet's call (licence).** Measured on real
   people (branch `diag/vosk-model`, run 39886586088):
   - The larger `vosk-model-en-us-0.22-lgraph` hears no more than the small model (90.6% against
     91.6%) at about 6× the CPU. Voice 0.3.7 stopped calling it "more accurate" in Settings.
   - `vosk-model-en-us-daanzu-20200905-lgraph`, used only as Voice's command recognizer (the
     small model staying the open one), takes Voice from 91.6% to 94.7% of words right ("eight"
     82% → 93%, "up" 85% → 96%), with no destructive presses. The same on a second run.
     - Cost: about 2× the CPU while listening, 245 MB more memory, a 133 MB download.
     - Its licence is **AGPL-3.0** (its own LICENSE.txt). Shipping it inside the installers needs
       Bennet's decision, perhaps a lawyer's. Offering it as an optional download in Settings is
       the other route.
     - The code change: Voice's `Listener` holds two models (`_make_recognizers` in `audio.py`).
     - It made Zoom worse (52 zooms an hour of talk), so Zoom keeps the small model.
8. **By ear on a real Mac:** GazeStage's built-in instrument rests 10 s after the last sound
   and wakes on hover (#60); check that the first note after a rest isn't late.
9. **Spanish** (#83, and Voice 0.4.0 on branch `voice/languages` if it hasn't merged yet):
   - Ask a Spanish-speaking musician to read `apps/voice/limitless_voice/languages/es.yaml` (the
     phrases and replies) and the Spanish words in `shared/hub/limitless_hub/web/index.html`
     (the `strings-es` table), and to say the commands to Voice with Logic open.
   - On the Mac: set Limitless Sound's language to Español and check that Voice offers its
     Spanish model, and that the replies come in a Spanish voice (System Settings ›
     Accessibility › Spoken Content › System voice › Manage Voices adds one).
   - Zoom's voice commands are still English only.
10. **More DAWs for Voice.** Voice has Logic Pro, Pro Tools and Ableton Live 12 (#85). The
    research for FL Studio, REAPER and GarageBand, each shortcut with its official source or
    marked unconfirmed, is in `apps/voice/DAW-SHORTCUTS.md`. With the DAW on the Mac, confirm the
    keys there and write the pack (`apps/voice/limitless_voice/packs/`), then add it to
    `stress/test_daw_keys_agree.py`. On a real Live 12, check the single-letter keys (S solo,
    C arm, O metronome) with Live's Computer MIDI Keyboard off.
11. **Press the corrected DAW keys once in the real DAWs** (#85): Logic's track mute and solo
    (M, S), Pro Tools' record (F12, on a laptop too), next/previous track (Control-; and
    Control-P) and go to end (Option-Return).

## Gotchas learned the hard way

- macOS CI runners have no window server: SDL falls back to the dummy driver, menu bars are
  skipped. Set `SDL_MAC_BACKGROUND_APP=1` for Control or SDL steals focus and shows a Dock icon.
- Vosk 0.3.45 has no Mac wheels; stay on 0.3.44.
- GazeStage PR builds need `CSC_FOR_PULL_REQUEST=true` or electron-builder ships a broken Mac
  signature. MediaPipe assets come from `apps/gazestage/scripts/fetch-assets.mjs`.
- DAW keys: every app must press the same key for the same thing, and
  `stress/test_daw_keys_agree.py` checks it. When first compared, the apps disagreed six times and
  one side was wrong each time (#85): Logic's track mute and solo are M and S (Control-M and
  Control-S act on regions); Pro Tools records on F12 (Command+Space is Spotlight on a Mac).
- On Apple silicon, reading the keyboard layout (TIS calls) off the main thread kills the app
  with a trap: use `mac_keys.py`, which hops to the main thread.
- The free plan runs at most 5 macOS jobs at once, and each macOS minute bills 10x (free while
  the repo is public). Workflows cancel a PR's superseded runs and run only the stress tests a
  change needs; keep it that way.
- `hdiutil create` on a runner sometimes says "Resource busy": use
  `.github/scripts/hdiutil-retry.sh`. `curl … | grep -q` under `pipefail` fails with curl's
  exit 23 when grep stops reading early; let grep read the whole page.
- PowerShell `Start-Process -Wait` also waits for every process the installer starts (an app it
  launches at the end): wait on the installer's own process (`WaitForExit`) instead, and give
  Inno Setup `postinstall` entries `skipifsilent`.
- `ps %cpu` on a Mac is a decaying average; measure idle CPU from CPU-time deltas instead.
- Shared CI runners add time unpredictably (GazeStage's first face on the Intel Mac runner:
  1.6 to 4.9 s for the same code over 13 builds). A timing check should judge what the code
  asked for (Zoom's microphone retry test records the waits it requests) or the fastest of a
  few tries (GazeStage's first face, #73), never one wall-clock reading against a tight line.
- A soak measures its whole test process, test code included: the hub soak once "leaked" 200 MB
  because the test kept every app link it had closed (#50). Before blaming the app, check what
  the test itself holds on to (`tracemalloc` snapshots show it in a minute).
- Python's `http.server` looks up the computer's network name when it starts (`socket.getfqdn`),
  which can wait 35 s on a Mac's multicast DNS: Control took 37 s to start that way (#52). Any
  new local web server must override `server_bind` the same way Control's and the hub's do.
- In Electron, `new AudioContext()` blocks the page that makes it until the audio device answers
  (twice, up to 10 s each). GazeStage's built-in instrument plays in a hidden page of its own for
  that reason (#54); never make one in a window that has to stay responsive.
- To find where an app hangs on a CI Mac, push a throwaway workflow that runs it with
  `faulthandler.dump_traceback_later(5, repeat=True)` and samples the built app with macOS's
  `sample` (branch `diag/control-startup` has the one that found #52).
- To find what keeps an app busy while idle, measure each of its processes from CPU-time deltas,
  then switch parts off one at a time and measure again (branch `diag/gazestage-idle` drives the
  built GazeStage with Playwright that way; it found all three causes in #60). The proof now names
  each app's busiest processes when it's over the limit (#62).
- An Electron page sitting idle should change nothing and ask for no frames. Rewriting the same
  DOM every second, or calling `requestAnimationFrame` from a timer, kept GazeStage's GPU process
  and renderer busy (#60). Write only what changed, and run idle checks straight from the timer.
- A running Web Audio context costs about 2.5% of a Mac's CPU even when silent. GazeStage suspends
  its own 10 s after the last sound and wakes it as the pointer settles on something that will
  sound (#60).
- An app copied onto a fresh CI Mac shares the computer with Spotlight indexing it for the first
  minutes. Zoom's idle CPU on Intel went from 0.9% to 5.2% between 15 s windows of the same run.
  Before blaming a part of an app, measure with and without it at the same point in time.
- GitHub's workflow-runs API sometimes answers a `branch=` or `status=` query with no runs at
  all. List runs unfiltered and pick on your side (`.github/scripts/newest-builds.sh`, #51).
- On Windows, Python's faulthandler also reports exceptions that were handled (COM's
  0x8001010d): the crash log drops a run's lines when the app closes normally (#53).
- Never make an RtMidi (`@julusian/midi`) Output just to list ports: on a Mac each one sets up a
  CoreMIDI client, which held up GazeStage's main process and slowed its start by a second on
  an Intel Mac, every 4 s, and never gave the clients back (#67). Any open output lists them all.
- A local settings page should wait for news (long polling), not ask every 150 ms: Control's
  page did, which was most of Control's idle CPU on the proof's Intel Mac (#65).
- The website must pass `.github/scripts/site-a11y.cjs` (axe-core, WCAG 2.2 AA, light and dark,
  desktop and phone); the Website workflow runs it on every `docs/` change (#66). Hover states
  aren't checked by it: keep white text on darker hovers, not lighter ones.
- Windows: `Start-Process` on a file marked as downloaded asks first and is "canceled by the
  user" with nobody to click; start it with `UseShellExecute = $false`. Python writes files and
  pipes in the old code page there, so write UTF-8 explicitly.
- Chromium burns CPU when idle if anything runs a 60 fps animation frame loop or keeps an
  AudioContext running: GazeStage sleeps its loop and rests its audio when nothing moves.
- Cloud sessions couldn't download Actions logs or artifacts. On the Mac,
  `gh run view --log-failed` and `gh run download` just work.
- Cloud sessions' network blocked alphacephei.com (Vosk models), huggingface.co and openslr.org,
  so speech models were measured in CI, not in the session. A cloud container can also restart
  and lose a background agent's uncommitted work: commit and push early.
- Limitless Sound's page has every English word in Spanish too. `test_languages.py` fails when a
  new English word on the page has no Spanish entry: add one to the `strings-es` table.
