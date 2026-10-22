# Limitless Sound: handoff for Claude Code

**Bennet:** open Claude Code in a folder on your Mac and paste this whole file in, or say
"Read HANDOFF-CLAUDE-CODE.md in github.com/chittychitty38/Limitless-sound and pick up the project."
Written 2026-10-22, after the 0.2.0 release. Everything below is the state of the project then.

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
| Limitless Sound | `shared/hub` | Joins the apps into one suite (any input can trigger any app); the guided setup and shared settings | Python stdlib only | 0.2.0, in the suite |
| Limitless Voice | `apps/voice` | Offline voice commands for Logic, Pro Tools and the computer | Python 3.12, PySide6, Vosk 0.3.44, PyInstaller | voice-v0.3.3 |
| Limitless One-Hand | `apps/one-hand` | Keys under one hand become DAW commands; hold Space to mirror-type | Python, PySide6, Quartz event tap / Win hook | one-hand-v0.2.1 |
| Limitless Zoom | `apps/zoom` | Zoom the DAW or screen by voice, one hand, dwell or a switch | Python, PySide6, pynput, Vosk | zoom-v0.1.1 |
| Limitless Color | `apps/color` | Recolors the whole screen for colorblind musicians | Rust, Tauri 2, Swift ScreenCaptureKit + Metal overlay | color-v0.1.3 |
| Limitless Control | `apps/control` | Xbox Adaptive Controller, switches, gamepads as DAW keys | Python, pygame-ce (SDL2), local web settings page | control-v0.2.2 |
| GazeStage | `apps/gazestage` | Play instruments and run the transport with eyes, head, a sound or a switch | Electron 39, MediaPipe face landmarks in a worker, virtual MIDI ports | gazestage-v0.3.3 |
| **Suite** | `packaging/` | One download with everything: a standard Mac installer (`.pkg`) and a Windows installer (`.exe`) | `suite.yml` | **v0.2.0** (the repo's Latest release) |

Every app meets **Limitless Access Standard level 2 (Adaptive)**: it follows the shared text
size, high contrast and reduced motion live and reports `prefs.applied`. Every app keeps a log
file (Limitless Sound's page › Activity › **Open the log folder**).

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
play, how should things look; it opens the apps that fit and sets the shared settings.
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
joins the suite, presses every action it offers, and measures start time and idle CPU. Its
results go on the website's Proof section. It runs on a pull request that changes the proof,
and nightly (or with "Run workflow") once the default branch is `main` (open item 3).

## Public website and branding

- Live: **https://chittychitty38.github.io/Limitless-sound/** (capital L; always share that one).
- Source: `docs/index.html` on `main`. GitHub Pages serves the `gh-pages` branch, a flat copy of
  `docs/`. After changing `docs/`, copy it to `gh-pages` and push, or ask Bennet to switch Pages
  to "main /docs" in repo settings so it updates by itself.
- Each app's Download link finds that app's newest release by itself (GitHub's API, in the page);
  the version written in the page is only the fallback.
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
- Voice's accuracy has only been measured on synthetic speech clips.
- The C++ client has only been tested against the hub, not inside a real plug-in host.
- No musician with a disability has tried any of it yet.

## Open items

1. **Hands-on Mac test.** Follow `HANDOFF.md`. It walks Bennet through installing the suite,
   the guided setup, running the stress tests on the real Mac, and checking each app by hand,
   recording results in `HANDOFF-RESULTS.md`. Fix what fails, one PR per app, and release
   fixes by bumping versions.
2. **GazeStage 0.4, PR #21** (branch `gazestage/xy-tone-pad`): the tone pad, an XY controller
   from Bennet's Jason Becker / Line 6 Helix idea. Two CCs (default 16/17; Helix profile CC1/CC2
   = EXP1/EXP2), sends to a USB Line 6 device if one is plugged in, else the "GazeStage Notes"
   port. Hub actions `gaze.tone`, `gaze.xy.*`. **Untested with a real Helix**, and far behind
   `main` now: merge `main` in, re-check, test with a Helix if Bennet has one, bump to 0.4.0.
3. **Default branch → `main`.** The repo's default branch is still `zoom-view-control`. Ask
   Bennet to change it at **GitHub › the repo › Settings › General › Default branch** (or run
   `gh repo edit chittychitty38/Limitless-sound --default-branch main` with his OK). Until then
   the nightly proof and nightly stress runs don't run, no workflow can be started by hand, and the
   suite installers aren't refreshed after an app release (see "How releases work").
4. **Signing.** Apple Developer ID ($99/year) for a signed, notarized `.pkg`, and a Windows
   certificate for the installers. Bennet's decision; once he has them, add them as repo secrets.
   Voice's workflow already signs and notarizes when the `APPLE_*` secrets exist; the other
   apps and the suite `.pkg` need the same steps added.
5. **Known bugs sent to app threads, check they're fixed:** Voice "delete fifty times" (should
   cap at 3 presses), Control trigger threshold without hysteresis.
6. **Clean up stale branches** (many old `claude/*`, `suite/*` and app branches whose PRs are
   merged). Ask Bennet first; cloud sessions weren't allowed to delete them.

## Gotchas learned the hard way

- macOS CI runners have no window server: SDL falls back to the dummy driver, menu bars are
  skipped. Set `SDL_MAC_BACKGROUND_APP=1` for Control or SDL steals focus and shows a Dock icon.
- Vosk 0.3.45 has no Mac wheels; stay on 0.3.44.
- GazeStage PR builds need `CSC_FOR_PULL_REQUEST=true` or electron-builder ships a broken Mac
  signature. MediaPipe assets come from `apps/gazestage/scripts/fetch-assets.mjs`.
- Verified DAW keys: Logic mute/solo are M/S (Ctrl+M mutes regions); Pro Tools record is F12
  (Cmd+Space is Spotlight).
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
- Chromium burns CPU when idle if anything runs a 60 fps animation frame loop or keeps an
  AudioContext running: GazeStage sleeps its loop and rests its audio when nothing moves.
- Cloud sessions couldn't download Actions logs or artifacts. On the Mac,
  `gh run view --log-failed` and `gh run download` just work.
