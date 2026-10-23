# Limitless Sound: handoff for Claude Code

**Bennet:** open Claude Code in a folder on your Mac and paste this whole file in, or say
"Read HANDOFF-CLAUDE-CODE.md in github.com/chittychitty38/Limitless-sound and pick up the project."
Written 2026-10-23, after the 0.2.10 release. Everything below is the state of the project then.

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
   which DAWs he has (Logic Pro, Pro Tools, Ableton Live, GarageBand, REAPER, FL Studio) and which hardware is with him today
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
| Limitless Sound | `shared/hub` | Joins the apps into one suite (any input can trigger any app); the guided setup, shared settings and language | Python stdlib only | 0.2.6, in the suite |
| Limitless Voice | `apps/voice` | Offline voice commands for Logic, Pro Tools, Ableton Live, GarageBand, REAPER, FL Studio and the computer | Python 3.12, PySide6, Vosk 0.3.44, PyInstaller | voice-v0.4.4 |
| Limitless One-Hand | `apps/one-hand` | Keys under one hand become DAW commands; hold Space to mirror-type | Python, PySide6, Quartz event tap / Win hook | one-hand-v0.2.7 |
| Limitless Zoom | `apps/zoom` | Zoom the DAW or screen by voice, one hand, dwell or a switch | Python, PySide6, pynput, Vosk | zoom-v0.1.10 |
| Limitless Color | `apps/color` | Recolors the whole screen for colorblind musicians | Rust, Tauri 2, Swift ScreenCaptureKit + Metal overlay | color-v0.1.5 |
| Limitless Control | `apps/control` | Xbox Adaptive Controller, switches, gamepads as DAW keys | Python, pygame-ce (SDL2), local web settings page | control-v0.2.8 |
| GazeStage | `apps/gazestage` | Play instruments and run the transport with eyes, head, a sound or a switch | Electron 39, MediaPipe face landmarks in a worker, built-in instrument in a hidden page of its own, virtual MIDI ports, XY tone pad | gazestage-v0.4.4 |
| **Suite** | `packaging/` | One download with everything: a standard Mac installer (`.pkg`) and a Windows installer (`.exe`) | `suite.yml` | **v0.2.10** (the repo's Latest release) |

Every app meets **Limitless Access Standard level 2 (Adaptive)**: it follows the shared text
size, high contrast and reduced motion live and reports `prefs.applied`. Every app keeps a log
file (Limitless Sound's page › Activity › **Open the log folder**).

Every screen works with a screen reader and the keyboard alone, and CI checks it: the web-based
screens (Limitless Sound's page, Control's page, GazeStage, Color, the Mac installer) pass WCAG 2.2
AA in every look with a keyboard walk (`.github/scripts/apps-a11y.cjs`, `screens.yml`, #79), and
the Qt apps have `tests/test_accessibility.py` (#75). Every app presses the same key for the
same thing in the same DAW (`stress/test_daw_keys_agree.py`, #85). Voice's setup guide and main
window grow as wide as their words need and scroll up and down for the rest (`look.UpAndDown`,
#103), and so do Settings' contents, with Save and Cancel always in view (0.4.4): before, at
double text, the setup guide cut off parts of 24 lines and Settings was 972 px wide.
Nothing scrolls sideways: the website at double text on a 320 px phone (#113), and every web
screen at every look (`apps-a11y.cjs` fails on any sideways scroll, #116; Limitless Sound's own
setup did, at 51 px, until hub 0.2.6).

**English and Spanish.** One shared language (`language`, "en" or "es") in Limitless Sound's
settings, chosen in the first two questions or from the computer's language, and every app
follows it live, in place, without moving the keyboard focus:
- Voice understands and answers in Spanish (0.4.0, #90), and its windows are in Spanish (0.4.1,
  #92). Its Spanish words, commands and replies are one file, `languages/es.yaml`; the windows ask
  for theirs with `ui.text("…")` (`words.py`).
- One-Hand and Zoom (`words.py` in each, #89), Control's page and GazeStage (a `strings-es` table
  in the page, #91), Limitless Sound's page (#83) and the installers (#87) are in Spanish.
- Color is in Spanish, and its offline helper understands Spanish descriptions (0.1.5, #95): on a
  blind set written by someone who never saw its rules, 98.3% of Spanish and 96.7% of English
  descriptions (English was 61.7% before). `cargo run -p color-core --example helper_report`.
- Zoom understands voice commands in Spanish (0.1.6, #97), measured on real people: 90-91% of
  its command words heard, 1-2 mistaken zooms in an hour of Spanish read aloud (English: 3.8).
  It also listens for 325 common Spanish words so talk isn't heard as a command.
- The website is in Spanish at `/es/` (`docs/es/index.html`, #93).
- Every one has a test that fails on English with no Spanish, and the Spanish fits at double
  text size wherever the English does.
- Not yet in Spanish: the guides on GitHub.

**A Brazilian Portuguese preview, in Voice only** (0.4.3, #103). Limitless Sound's language list
offers «Português (prévia: só o Limitless Voice)» (hub 0.2.5); the page and every other app stay
in English for it. Every app shows English for a suite language it doesn't have: One-Hand and Zoom
used to keep the last one, so Español → Português left them in Spanish (One-Hand 0.2.7, Zoom
0.1.9, #106).
- Voice's Portuguese is one file, `apps/voice/limitless_voice/languages/pt.yaml`, with Alpha
  Cephei's `vosk-model-small-pt-0.3` (31 MB, Apache 2.0; their only other Portuguese model is
  1.6 GB and GPL).
- On real Brazilian speakers it gets 62% of command words right at once, against 83.5% in
  Spanish. The speech model is the limit: it hears nothing in 33% of clips (Spanish's: 4%), and
  gets 27.4% of read words wrong (Spanish's: 14.8%). Settings says so in Portuguese.
- The same safety rules as Spanish: Cut, Paste and Delete only on the exact word, a command word
  inside a sentence is talk. One command an hour of Portuguese read aloud, none destructive.
- `stress.yml` measures it (MSWC pt and FLEURS pt_br) on every Voice change.

Release links (permanent; they always point at the newest suite):
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-apple-silicon.pkg
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-intel.pkg
- https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-windows.exe
- All releases, including each app's own: https://github.com/chittychitty38/Limitless-sound/releases

Nothing is signed. macOS needs **System Settings → Privacy & Security → Open Anyway** once,
Windows SmartScreen needs **More info → Run anyway**. Signing needs an Apple Developer ID and a
Windows code-signing certificate, which Bennet doesn't have yet; the builds are ready for them
(`SIGNING.md`, open item 4).

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
- `SIGNING.md`: Bennet's guide to the certificates and secrets. `.github/scripts/mac-sign.sh` and
  `win-sign.ps1` do the signing; `signing.yml` tests them with throwaway certificates.
- `translations/`: the native speakers' read (`es.md`, `pt.md`), with the two report forms in
  `.github/ISSUE_TEMPLATE/`.
- `.github/workflows/branches.yml`: deletes branches whose pull request was merged (open item 5).
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
item 3). Until then the website and README say the proof runs "with every release", which is
what has happened; say "every night" again once the nightly runs do. Each run records the
versions of every app and of Limitless Sound's page (the hub) and the page's idle load. The
README's badge (`.github/scripts/proof-badge.py`, from `latest.json`, #113) says how many of the
three computers the latest release passed on; it lives at `proof/badge.svg` on `gh-pages`.

Its runs on 0.1.0 to 0.2.1 found every bug fixed in 0.2.0 to 0.2.2: Zoom crashing on Apple
silicon, Control taking 37 s to start, GazeStage leaving actions unanswered on a Mac without
working audio, Zoom's and GazeStage's idle CPU, and false crash logs on Windows. **0.2.10 passes it
on all three computers, twice** (runs 40016678351 and 40020260322; the second is on the website
and the README's badge):
- Every app is ready in under 7 s, at Access Standard level 2, with every action answered and no
  timeouts. The installer takes 12–17 s on Apple silicon, 17–19 s on Intel and 48 s on Windows.
- Every suite check is green, S1 to S7:
  - Limitless Sound's own page opens, with its Spanish words (S4, #86);
  - the suite's language can be set to Español and back (S5, #88);
  - One-Hand, Zoom, Control, GazeStage and Color each say they're showing Spanish within 3 s of
    the suite switching, and English again after (S6, #96, #100). Voice is named but not held: it
    reports the language it listens in, English until its Spanish model is downloaded.
  - From Español, Português leaves every app but Voice in English within 3 s (S7, #107). Each
    must show Spanish first, so an app that ignores the switch can't pass.
- Every app is under 3% of the CPU sitting idle on every computer in both runs, and Limitless
  Sound's page (hub 0.2.6) 0.5% or less. All but Zoom stay at 1.6% or less. Zoom on the Intel Mac
  sat at the 3% line through 0.2.9 (2.7–3.7%); one cause was that it asked macOS about every one
  of its permissions every second. Zoom 0.1.10 asks only about the two it needs, every 5 s while
  one is missing and every 10 s once both are granted (#111). In 0.2.10 it read 0.9% and then
  2.5% (and 0.1% then 1.5% on Windows), so something else still wakes it now and then (open
  item 12).
- P3 watches an app over 3% once more, 30 s later, and judges that reading (#107): one 15 s
  reading can't tell a spike from steady use (Zoom on Intel read 3.7% and 2.9% in two runs of
  the same 0.2.9).
- P5 (#104) compares each app's idle memory with the last published proof on the same kind of
  computer and warns at 1.5x and 50 MB more. The 0.2.7 proof found Zoom 0.1.6 at twice its
  memory (510 MB on Apple silicon) and 5.3% idle CPU on Intel: it loaded its speech model again
  on each language switch. Zoom 0.1.8 (#101) fixed it: 186–193 / 253 / 248 MB in 0.2.10.

An app over the limit names its busiest processes (#62). To run it again before the default
branch is `main`, open a PR that touches `packaging/proof/`, then publish its results: point the
`proof-results` branch at a commit with the tree of `proof-results-test` (`git commit-tree`), and
copy its `latest.json` and `badge.svg` to `proof/` on `gh-pages`.

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
- Nobody who speaks Spanish or Portuguese has used any of it: Voice was measured on recordings
  of Spanish and Brazilian speakers (Common Voice, FLEURS, MSWC), and every word was written
  without a native speaker's read.
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
3. **Default branch → `main`.** The repo's default branch is still `zoom-view-control`. Bennet
   said yes to changing it, but cloud sessions can't change repo settings. On the Mac, with his
   OK, run `gh repo edit chittychitty38/Limitless-sound --default-branch main`, or he clicks
   **GitHub › the repo › Settings › General › Default branch › ⇄ (Switch to another branch) ›
   main › Update**. Until then the nightly proof and nightly stress runs don't run, no workflow
   can be started by hand, and the suite installers aren't refreshed after an app release (see
   "How releases work"). While there: **Settings › General › Pull Requests › Automatically
   delete head branches** stops new branches piling up.
4. **Signing: the builds are ready, the certificates are Bennet's decision** (#115).
   `SIGNING.md` walks him through it in plain words. Every build signs once its secrets exist and
   stays exactly as now until then.
   - Mac: Bennet is already in the Apple Developer Program (he said so on 2026-10-23). Left: two
     certificates (Developer ID Application and Developer ID Installer) saved as .p12, an
     app-specific password, nine repo secrets (`SIGNING.md` steps 2 to 6). Then either
     **Actions › Limitless Sound Suite › Run workflow** (needs the default branch to be `main`,
     item 3), or a new suite version in `packaging/VERSION`, which builds, signs, notarizes and
     releases it on its own. Every app, the suite `.pkg` and its notarization go through
     `.github/scripts/mac-sign.sh`; GazeStage and Color feed the same secrets to electron-builder
     and Tauri.
   - Windows: since June 2023 a new code-signing certificate can't be downloaded as a .pfx file,
     which is all `.github/scripts/win-sign.ps1` signs with. He has to pick a cloud signing
     service first (Azure Trusted Signing, about $10 a month, or SSL.com eSigner); then connect it
     in `win-sign.ps1` and GazeStage's workflow.
   - The **Signing check** workflow signs, installs and runs real builds with throwaway
     certificates from a throwaway authority whenever the scripts change. Notarization can't be
     tried without Apple: the first real signed build is its first test.
   - Ask before buying anything or adding secrets. Once a signed build works, take the
     **Open Anyway** / **Run anyway** steps out of the README, the site and the release notes.
5. **Clean up merged branches.** Bennet said to delete the merged ones only. Once the default
   branch is `main` (item 3): **Actions › Clean up merged branches › Run workflow**, first with
   "Only list what would be deleted" ticked (#109). It deletes a branch only when its pull request
   was merged with that same last commit, and keeps `main`, `gh-pages`, `proof-results`,
   `proof-results-test`, `zoom-view-control` and every unmerged branch. A deleted branch can be
   restored from its pull request's page. The throwaway `diag/*` branches have no merged PR, so
   they stay: ask Bennet before deleting those.
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
9. **Spanish, read by people who speak it.** Everything Spanish was written without a native
   speaker. Send a Spanish-speaking musician `translations/es.md` and a Brazilian one
   `translations/pt.md`: each, in their language, walks through installing, choosing the language,
   what to try and the words below, and links two report forms (`.github/ISSUE_TEMPLATE/`). Ask a
   session to "apply the open translation and voice issues" when they come in. What to read:
   - Voice: `apps/voice/limitless_voice/languages/es.yaml` (commands, replies, window words).
     Check "Decir en voz alta lo que pasa", "Ya lo hice, comprobar de nuevo", "Lo que se oyó",
     "Repetir la configuración…", "Deja que tu voz pulse las teclas", "De acuerdo" for OK. Voice
     says "aplicación" and “…”, the other apps "app" and «…»: pick one.
   - GazeStage (`apps/gazestage/renderer/index.html`, `strings-es`): "Avanzar" / "Rebobinar",
     "Pedal" for Hold notes, "Selección posando" for dwell, "mira para no parar", "silencio".
     These were shortened to fit at double text size; a better word must fit too (the smoke
     test checks).
   - The website (`docs/es/index.html`): the headline "Software de música para todos los
     cuerpos" (the "every body" pun), "Con franqueza: en qué punto estamos", "ratón" or "mouse",
     "83.5 %" or "83,5 %", the level names Conectado / Adaptable / Manos libres / Codiseñado, and
     the macOS buttons named for a Spanish Mac ("Abrir igualmente", «Chip» / «Procesador»).
   - Color (`apps/color/app/ui/index.html`, `strings-es`): "Afinador", "Ajústalo por mí",
     "Silenciar", "Soltar"/"Fijar", "Medidor: saturación", the sample session's track names, and
     the path "Ajustes del Sistema › Accesibilidad › Pantalla › Filtros de color".
   - Zoom's voice commands (`apps/zoom/README.md`, the Español table): «acercar»/«ampliar»,
     «alejar»/«reducir», «más altas»/«más bajas», «lupa», «ajustar», «repite». Nobody in the
     recordings said «acercar», «alejar» or «lupa» alone, so try them on the Mac's mic.
   - On the Mac: set Limitless Sound's language to Español, check Voice offers its Spanish model
     (39 MB) and that replies come in a Spanish voice (System Settings › Accessibility › Spoken
     Content › System voice › Manage Voices adds one), and that VoiceOver reads each window in
     Spanish.
   - Portuguese (Brazilian): `apps/voice/limitless_voice/languages/pt.yaml`, the preview note in
     Settings, and the hub's «Português (prévia: só o Limitless Voice)». Several labels were
     shortened to fit at double text («Abrir o Limitless Voice ao fazer login», «Agora não (sem
     isso os comandos não funcionam)», `Ouvindo: "vai dormir" para pausar`); a better phrase
     must fit too (`test_portuguese.py` holds it to the English). Is the preview worth keeping at
     62%, or should it wait for a better free model?
10. **Try the three new DAWs** (#99): Voice, Control, One-Hand and Zoom work in GarageBand 10,
    REAPER 7 and FL Studio, besides Logic Pro, Pro Tools and Ableton Live 12. Every key came
    from the maker's guide (Apple's, Cockos', Image-Line's), read through excerpts because the
    cloud session couldn't open those sites; anything unconfirmed was left out.
    `apps/voice/DAW-SHORTCUTS.md` starts with what shipped, each key's source, and ends with the
    checklist for a real Mac or PC. The main ones:
    - GarageBand: every shipped key, and Zoom's Command-arrow zoom keys (unconfirmed, kept).
      Then read Help › Main window shortcuts and add the cycle, metronome and zoom keys it gives.
    - REAPER: Cmd+M opens the mixer on a Mac (not Minimize); which way + and − zoom.
    - FL Studio: "record mode" then "play"; F5–F9 on a Mac; Page Up/Down and Shift+4 to zoom.
    - That each app notices each DAW in front (including `FL64 (scaled).exe`, older REAPER64.app).
    On a real Live 12, also check the single-letter keys (S solo, C arm, O metronome) with Live's
    Computer MIDI Keyboard off.
11. **Press the corrected DAW keys once in the real DAWs** (#85): Logic's track mute and solo
    (M, S), Pro Tools' record (F12, on a laptop too), next/previous track (Control-; and
    Control-P) and go to end (Option-Return).
12. **Zoom sitting idle on an old Intel Mac.** Under the 3% line in both 0.2.10 proofs, but it
    varies: 0.9% and 2.5% on the proof's Intel Mac (a 2012 Mac mini), 0.1% and 1.5% on Windows,
    while Voice, which has the same silence gate (`SpeechGate` in
    `apps/zoom/limitless_zoom/voice.py`), reads 0.3–0.9% on that Mac. The permission check every
    second was one cause (#111); the Spanish model download was ruled out (#107). Each reading is one 15 s window,
    and P3 only looks again above 3%. On a real Intel Mac, sample Zoom's threads for a few minutes
    at rest (py-spy, or macOS's `sample`) before changing anything.

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
- An app that can change its speech model (Voice, Zoom) must not load the same one again when
  nothing it listens with changes: each load costs a second of CPU and ~150 MB that Python
  keeps. Zoom 0.1.6 did it on every language switch and doubled its memory (#101). The proof's
  P5 now warns when an app's idle memory grows 1.5x over the last published proof.
- A test that times a child process times Python and Qt starting too (2.8 s on a busy Intel Mac
  runner): time the call inside the child instead (Zoom's `test_remote_command`, #99).
- Every app's Spanish has a test that fails on a word with no Spanish: add the Spanish next to
  the English (`strings-es` in a page, `words.py` in One-Hand and Zoom, `languages/es.yaml`
  `texts` in Voice). GazeStage's smoke test holds the Spanish to the English at double text size
  on the computer's own fonts. Ubuntu CI has DejaVu Sans, wider than a Mac's: to see what CI
  sees, run the smoke test with a fontconfig file that offers only DejaVu (`FONTCONFIG_FILE`).
- A Qt window doesn't make room for wrapped lines by itself, and Voice's setup window had a fixed
  620 x 520 minimum: at large text its pages squeezed their lines, and which label lost out
  flipped with the font, so Portuguese failed on Windows' CI where the English beside it happened
  to fit. Shortening words couldn't fix that. A window's contents go in `look.UpAndDown` (scrolls
  up and down, asks for the width they need), and no fixed minimum size stops a window growing.
  Compare a translation with English on the same machine, and check a few fonts locally
  (DejaVu Sans, Carlito, Liberation Sans) at 1x to 2.3x text before pushing.
- A page that's fine on a laptop can scroll sideways on a phone at double text: a grid column
  of `1fr` won't shrink below its longest word (use `minmax(0, 1fr)`), a `<select>` is as wide as
  its longest option (`max-width: 100%`), a fieldset won't shrink below its contents
  (`min-width: 0`), and long words need `overflow-wrap: anywhere`. A sticky header taller than a
  fifth of a phone's screen at double text hides what it scrolls over: the site's turns static
  then. `site-a11y.cjs` and `apps-a11y.cjs` check all of it.
- Qt's `QFormLayout.WrapLongRows` decides each row's wrap by its own label, but places every
  field after the longest label: one long label squeezes the short rows' fields. Keep labels
  short, or put the field under the label yourself.
- `productsign` takes only an installer certificate from an authority the Mac trusts and marked
  for installers alone: a self-signed one, or one that may also sign code, is "not an installer
  signing identity". Apple's real ones are fine; the Signing check's throwaway ones copy their
  shape (branch `diag/productsign` tried seven shapes on macOS 15).
- Cloud sessions couldn't change repo settings (the default branch) or delete branches; the
  session's network refused both. Do those from the Mac, with Bennet's OK.
- Before blaming a cause, find a measurement that could prove it wrong. Zoom's 3.7% idle in the
  first 0.2.9 proof looked like its Spanish model downloading after S6; P3's second look read
  3.2% then 3.3%, which ruled that out. One cause was in an old profile of its threads all along:
  a permission check every second (#111). A re-run of one proof job publishes the first attempt's
  results again (artifacts share a name): push a commit for a fresh run instead.
- GitHub's artifact storage can refuse downloads for a while ("HTTP 503: Egress is over the
  account limit"), after a day of many suite builds: each one downloads every app for three
  computers. On 2026-10-23 it refused Control's builds for over an hour. The suite build now takes
  such an app from its release instead (`newest-builds.sh`, #94), the same files made by the same
  run. An app's own release job can't, as it makes that release: re-run the failed job later.
