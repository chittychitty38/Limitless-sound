# Limitless Sound: handoff for Claude Code

**Bennet:** open Claude Code in a folder on your Mac and paste this whole file in, or say
"Read HANDOFF-CLAUDE-CODE.md in github.com/chittychitty38/Limitless-sound and pick up the project."
Written 2026-10-22. Everything below is the state of the project on that date.

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
2. Ask Bennet, in one message, which Mac he is on (Apple Silicon or Intel, macOS version),
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
  Ask before anything outside the repo (emails, public posts, paid services, signing certs).
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
| Limitless Voice | `apps/voice` | Offline voice commands for Logic, Pro Tools and the computer | Python 3.12, PySide6, Vosk 0.3.44, PyInstaller | **voice-v0.3.1** (0.3.0 before it) |
| Limitless One-Hand | `apps/one-hand` | Keys under one hand become DAW commands; hold Space to mirror-type | Python, PySide6, Quartz event tap / Win hook | **one-hand-v0.2.0** |
| Limitless Zoom | `apps/zoom` | Zoom the DAW or screen by voice, one hand, dwell or a switch | Python, PySide6, pynput, Vosk | none yet (0.1.0, only in the suite DMG) |
| Limitless Color | `apps/color` | Recolors the whole screen for colorblind musicians | Rust, Tauri 2, Swift ScreenCaptureKit + Metal overlay | none yet (0.1.1, only in the suite DMG) |
| Limitless Control | `apps/control` | Xbox Adaptive Controller, switches, gamepads as DAW keys | Python, pygame-ce (SDL2), local web settings page | **control-v0.2.1** |
| GazeStage | `apps/gazestage` | Play instruments and run the transport with eyes, head, a sound or a switch | Electron 39, MediaPipe face landmarks, virtual MIDI ports | **gazestage-v0.3.1** |
| Limitless Sound hub | `shared/hub` | Joins the six apps into one suite (any input can trigger any app) | Python stdlib only | in the suite |
| **Suite** | `packaging/` | One Mac download holding all of the above | `suite.yml` | **v0.1.0** (repo's Latest release) |

Release links:
- All releases: https://github.com/chittychitty38/Limitless-sound/releases
- Suite DMG (permanent links):
  - https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-apple-silicon.dmg
  - https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-intel.dmg
- Per app: `.../releases/tag/<tag>` for the tags in the table.

Nothing is signed. macOS needs **System Settings → Privacy & Security → Open Anyway**, Windows
SmartScreen needs **More info → Run anyway**. Signing needs an Apple Developer ID and a Windows
code-signing certificate, which Bennet doesn't have yet.

### How the hub works
Hub on 127.0.0.1: TCP 47900 (NDJSON, apps connect) and HTTP 47901 (settings page and one-shot
triggers like `/do/daw.record?t=<token>`). Discovery file `link.json` (port + token) in the shared
"Limitless Sound" config folder. Actions are `<tool>.<action>` (voice, onehand, zoom, color,
control, gaze, hub). Intents like `daw.play` go to whichever open app can press DAW keys.
"Sidechain links" are event → action routes (e.g. while recording, Voice only hears stop/wake
words). Spec: `shared/PROTOCOL.md`. Clients: `shared/clients` (Python), `apps/gazestage/limitless-link.js`,
`apps/color/app/src-tauri/src/limitless_link.rs`. Every app works alone without the hub.

## Where things live

- `README.md`, `CONTRIBUTING.md`: suite overview and per-app conventions.
- `apps/<app>/README.md`: each app's details and what has and hasn't been tested.
- `.github/workflows/<app>.yml`: one workflow per app (macos-15, macos-15-intel, windows-latest),
  path-filtered to its folder. `suite.yml` builds the suite DMG. `shared.yml` tests the hub.
- `packaging/VERSION`, `packaging/RELEASE.md`: suite version and how it is released.
- `standard/`: Limitless Access Standard draft 0.1 and its test kit (`standard/conformance/las_check.py`).
- `docs/`: the public website (also copied to the `gh-pages` branch).
- Stress tests and the hands-on Mac test script are on **PR #12** (branch
  `claude/project-thread-u6zwvi`): `stress/`, `.github/workflows/stress.yml`, `HANDOFF.md`,
  `docs/AUDIT.md`. Not merged yet.
- Older prototypes in Bennet's Claude project files (Karabiner one-hand, Hammerspoon zoom,
  AdaptiveMapper Swift, browser color tuner) are superseded by the apps above. Ignore them.

### How releases work
Each app's workflow has a release job: on a push to `main` with a new version, it publishes
`<folder>-v<version>` with Mac (Apple Silicon + Intel) and Windows builds, not marked Latest.
To release an app, bump its version and merge to `main`:
Voice `apps/voice/limitless_voice/__init__.py`, One-Hand `apps/one-hand/onehand/__init__.py`,
Zoom `apps/zoom/limitless_zoom/__init__.py`, Control `apps/control/limitless_control/__init__.py`,
Color `apps/color/app/src-tauri/tauri.conf.json`, GazeStage `apps/gazestage/package.json`,
suite `packaging/VERSION` (the suite release is the repo's Latest).
From your Mac you can also push tags normally; the cloud sessions couldn't (403).

## Public website and branding

- Live: **https://chittychitty38.github.io/Limitless-sound/** (capital L; always share that one).
- Source: `docs/index.html` on `main`. GitHub Pages serves the `gh-pages` branch, a flat copy of
  `docs/`. After changing `docs/`, copy it to `gh-pages` and push, or ask Bennet to switch Pages
  to "main /docs" in repo settings so it updates by itself.
- When an app gets a release, update its version chip and link on the site.
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
- **Limitless Access Standard** (`standard/`, draft 0.1): levels and a test kit built on the hub
  protocol. Level 2 needs apps to report `prefs.applied`; none of the six apps send it yet.
- **Heartmark concept 0.2** (Sam's idea; PDF in Bennet's project files,
  `vision/heartmark/Limitless-Heartmark-Concept.pdf`): the Heartmark as the compliance mark,
  "Made for Any Body" as the box line, a hardware track, six pillars (Reach, Connect, Sense,
  Adapt, Endure, Explain), the four levels, and a Limitless Builders program. Open calls for
  Bennet and Sam: final names, fund percentage (10% proposed), who holds the mark (nonprofit?),
  first partner (Line 6 or Kiesel).

## What has never been proven

Every app builds, installs and passes its automated tests and stress tests on GitHub's machines.
Those machines have no screen, mic, camera, controller, DAW or privacy permissions, so:
- No app has run on Bennet's Mac with his real mic, webcam, controller and DAW.
- Color's Mac overlay has never drawn on a real screen.
- Control has never seen a real Xbox Adaptive Controller.
- One-Hand's Mac self-test passes even if the key hook can't start; check it really types.
- GazeStage has never driven a real Pro Tools rig (HUI ports, rewind/ffwd/stop mapping).
- Voice's accuracy has only been measured on synthetic speech clips.
- No musician with a disability has tried any of it yet.

## Open items

1. **Hands-on Mac test.** Follow `HANDOFF.md` from PR #12
   (`git fetch origin claude/project-thread-u6zwvi && git show FETCH_HEAD:HANDOFF.md`). It walks
   Bennet through installing the suite DMG, running the stress suite on the real Mac, and
   checking each app by hand, recording results in `HANDOFF-RESULTS.md`. Where it names a
   branch for an app, use `main` instead; all six apps and the hub are merged now. Fix what
   fails, one PR per app, and release fixes by bumping versions.
2. **Merge PR #12** (stress tests). Before merging, drop the `xfail`/`@KNOWN_BUG` markers in
   `stress/test_hub_stress.py`: the hub fixes they waited for are on `main`. Rebase on `main`.
3. **GazeStage 0.4, PR #21** (branch `gazestage/xy-tone-pad`): the tone pad, an XY controller
   from Bennet's Jason Becker / Line 6 Helix idea. Two CCs (default 16/17; Helix profile CC1/CC2
   = EXP1/EXP2), sends to a USB Line 6 device if one is plugged in, else the "GazeStage Notes"
   port. Hub actions `gaze.tone`, `gaze.xy.*`. **Untested with a real Helix.** If Bennet has
   one, test it, then rebase on `main`, merge, and the release job publishes 0.4.0.
4. **Zoom and Color standalone releases.** They're only inside the suite DMG. Unlike the other
   apps, `zoom.yml` and `color.yml` still release only on a pushed tag (`zoom-v*`, `color-v*`),
   which cloud sessions couldn't push. Zoom's release step already sets `make_latest: "false"`;
   Color's doesn't yet, so add it or Color would replace the suite as the repo's Latest. With
   Bennet's go-ahead, push `zoom-v0.1.0` and `color-v0.1.1` from the Mac (or add the same
   "release on main when the version is new" job the other apps have), then update the site.
5. **Default branch → `main`.** The repo's default branch is still `zoom-view-control`. Ask Bennet
   to change it at https://github.com/chittychitty38/Limitless-sound/settings (General → Default
   branch), or run `gh repo edit chittychitty38/Limitless-sound --default-branch main` with his OK.
   Until then `workflow_run` triggers don't fire, so after any app release refresh the suite DMG
   by hand: `gh workflow run suite.yml -R chittychitty38/Limitless-sound --ref main`.
6. **Signing.** Apple Developer ID ($99/year) for notarized DMGs, Windows certificate for the
   installers. Bennet's decision; once he has them, add them as repo secrets.
7. **Access Standard level 2.** Have each app send `prefs.applied` to the hub.
8. **Known bugs sent to app threads, check they're fixed:** Voice "delete fifty times" (should cap
   at 3 presses), Control trigger threshold without hysteresis.
9. **Clean up stale branches** after the above merges (many old `claude/*`, `suite/*`, app branches).

## Gotchas learned the hard way

- macOS CI runners have no window server: SDL falls back to the dummy driver, menu bars are
  skipped. Set `SDL_MAC_BACKGROUND_APP=1` for Control or SDL steals focus and shows a Dock icon.
- Vosk 0.3.45 has no Mac wheels; stay on 0.3.44.
- GazeStage PR builds need `CSC_FOR_PULL_REQUEST=true` or electron-builder ships a broken Mac
  signature. MediaPipe assets come from `apps/gazestage/scripts/fetch-assets.mjs`.
- Verified DAW keys: Logic mute/solo are M/S (Ctrl+M mutes regions); Pro Tools record is F12
  (Cmd+Space is Spotlight).
- macOS runners bill 10x minutes. The repo is public so Actions are free; keep it public or
  watch the spending limit (it ran out once, on 2026-10-21).
- Cloud sessions couldn't download Actions logs or artifacts, so CI surfaces errors as
  `::error::` annotations. On the Mac, `gh run view --log-failed` and `gh run download` just work.
