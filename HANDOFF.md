# Limitless Sound: hands-on testing on a real Mac

**Bennet:** open Claude Code on your Mac in an empty folder and paste this whole file in (or
say "Follow HANDOFF.md from github.com/chittychitty38/Limitless-sound"). Claude Code will set
everything up, run the automated tests on your real Mac, then walk you through the hands-on
checks one at a time. Have nearby whatever you have of: Logic Pro, Pro Tools, a USB or built-in
mic, a webcam, the Xbox Adaptive Controller (plus any switches or foot pedal), and headphones.
You can stop at any point; progress is saved in `HANDOFF-RESULTS.md`.

Why this is needed: the apps build, install and pass every automated and stress test on GitHub's
machines, but those machines have no screen, mic, camera, controller, DAW or privacy permissions.
[docs/AUDIT.md](docs/AUDIT.md) lists exactly what has and hasn't been proven.

---

## Instructions for Claude Code

You are helping Bennet, who builds accessible music software, test the Limitless Sound apps on
his own Mac for the first time. He is the tester, not a developer on this session: explain each
step in plain words, ask him to do one physical thing at a time, and wait for his answer. Never
change his system settings yourself; tell him where to click. Record every result as you go.

### 1. Ask first

Ask Bennet, in one message: which Mac (Apple Silicon or Intel) and macOS version, which of
Logic Pro / Pro Tools / Ableton Live he has installed, and which hardware he has with him today
(mic, webcam, Xbox Adaptive Controller, switches, foot pedal). Skip the checks that need
something he doesn't have, and mark them "not tested: no <thing>".

Create `HANDOFF-RESULTS.md` in the repo folder with his answers and today's date. For every
check below, write one line: ✅ pass, ❌ fail, or ⏭ skipped, plus what he saw in his words.

### 2. Get the code and the apps

```sh
xcode-select -p >/dev/null 2>&1 || xcode-select --install     # wait for it to finish
command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install gh python@3.12 node@22 rustup-init
gh auth status || gh auth login                                 # Bennet signs in to GitHub
gh repo clone chittychitty38/Limitless-sound LimitlessSound && cd LimitlessSound
```

Every app and the hub are on `main`, and the whole suite is one released Mac download. Test the
**installed apps** (what a musician would get), not source runs. Download the suite for his chip:

```sh
mkdir -p downloads && cd downloads
curl -fLO https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-apple-silicon.dmg
# Intel Mac: Limitless-Sound-Suite-mac-intel.dmg
cd ..
```

To test a fix that isn't released yet, download the newest successful build of that app's
workflow instead:

| App | Folder | Workflow | Mac download (artifact) |
|---|---|---|---|
| Limitless Sound hub | `shared/hub` | `shared.yml` | `Limitless-Sound-mac-apple-silicon` / `-mac-intel` |
| Limitless One-Hand | `apps/one-hand` | `one-hand.yml` | `Limitless-One-Hand-mac-…` |
| Limitless Voice | `apps/voice` | `voice.yml` | `LimitlessVoice-mac-…` |
| Limitless Zoom | `apps/zoom` | `zoom.yml` | `Limitless-Zoom-mac-…` |
| Limitless Color | `apps/color` | `color.yml` | `Limitless-Color-mac-…` |
| Limitless Control | `apps/control` | `control.yml` | `LimitlessControl-mac-…` |
| GazeStage | `apps/gazestage` | `gazestage.yml` | `GazeStage-mac-…` |

```sh
WF=one-hand.yml; BRANCH=main          # or the fix's branch
RUN=$(gh run list -w "$WF" -b "$BRANCH" -s success -L 1 --json databaseId -q '.[0].databaseId')
gh run download "$RUN" -D "downloads/$WF"     # artifact names end in -mac-apple-silicon or -mac-intel
```

If the artifact names differ, list them with `gh api repos/chittychitty38/Limitless-sound/actions/runs/$RUN/artifacts -q '.artifacts[].name'`.

Open the suite `.dmg` and have Bennet double-click **Install Limitless Sound**; it copies every
app into Applications (a single app's `.dmg` from a workflow build is dragged there instead).
The apps aren't signed yet, so the first time macOS refuses: he goes to **System Settings →
Privacy & Security**, scrolls down and clicks **Open Anyway**. Record how many clicks that took and whether anything
was confusing; that is what every musician will meet.

### 3. Run the automated stress tests on this Mac

These are the same tests CI runs, but on real Apple hardware, with the Mac's own voices for
speech. Set up once:

```sh
python3.12 -m venv .venv && source .venv/bin/activate
pip install pytest psutil numpy pyyaml platformdirs pygame-ce==2.5.8 vosk==0.3.44
```

Then, from the repo root on `main`:

```sh
python -m pytest stress -v -s
```

(To stress a fix on another branch, `git worktree add ../ls-fix origin/<branch>` and run with
`STRESS_REPO_ROOT=../ls-fix`.) Voice with the real recognizer and real Mac voices:

```sh
curl -sSfLO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && unzip -q vosk-model-small-en-us-0.15.zip
python stress/tools/make_speech.py /tmp/ls-speech
VOSK_MODEL=$PWD/vosk-model-small-en-us-0.15 TTS_WAV_DIR=/tmp/ls-speech python -m pytest stress/test_voice_stress.py -v -s
```

GazeStage (uses a fake camera, so no face needed yet) and Color:

```sh
(cd apps/gazestage && npm ci && node ../../stress/gazestage_stress.mjs)
rustup-init -y && source ~/.cargo/env
cargo test --release --manifest-path stress/color/Cargo.toml -- --nocapture
```

Record each result. GazeStage prints its frame rate: on a real Mac it should be 30 or more.

### 4. Hands-on checks

The nightly proof run (`.github/workflows/proof.yml`, results on the website's Proof section)
already installs the public download on fresh Apple silicon and Intel Macs and a Windows PC,
opens every app and presses every one of its actions. So these checks are only what a build
machine can't do: a real microphone, camera, controller and DAW, the permission prompts, and
how it feels.

Do them app by app, in this order (each builds on the last). Before each app, tell Bennet in two
sentences what it does and what he'll be checking. If something fails: write down exactly what
he did and saw, attach the app's log from `~/Library/Logs/Limitless Sound/` (one file per app,
plus a `crash.log` if it died) and any crash report from Console.app › Crash Reports, take a
screenshot, then continue. At the end, fix what you can on a branch and open a pull request per
app, or open an issue.

#### First: the guided setup (everything else builds on it)
- [ ] Right after installing, the Limitless Sound page opens and asks **How do you like to play?**
      Bennet picks what fits him, then a text size. The page previews the size as he picks.
- [ ] **Set up my apps** opens the chosen apps. Each card on My apps says "✓ Uses your text size,
      contrast and motion settings" within a few seconds.
- [ ] Settings › change text size to **Largest** and turn on **High contrast**: every open app
      (Voice's window, One-Hand's window and badge, Zoom's panel, Control's settings page,
      Color's tuner, GazeStage) grows and turns high contrast within about 3 seconds, without
      restarting any of them. Turn both off again: they all go back.
- [ ] Each app opens in under 5 seconds (Control used to take 37).

#### Limitless One-Hand (needs Logic Pro or Pro Tools)
- [ ] First launch: macOS asks for **Accessibility** and **Input Monitoring**. After turning both
      on, One-Hand says it's ready without a restart (or clearly asks for one).
- [ ] Double-tap Shift turns one-hand mode on and off, with a sound and the ON badge.
- [ ] In Logic: the left-hand keys do what the on-screen card says. Check at least Record, Undo,
      Go to start, Back/Forward one bar, Zoom in/out, Mute, Solo.
- [ ] **Hold** Record (E) for two full seconds: Record toggles **once**. (This was a bug; it
      fired ~5 times per press before the stress-test fix.)
- [ ] Hold Back one bar: the playhead keeps moving while held (bar and zoom keys repeat on purpose).
- [ ] With one-hand mode on, ⌘S still saves and typing with Shift for capitals works in a text field.
- [ ] Hold space and type a mirrored letter (space+F types J for a left-hander).
- [ ] Switch to Pro Tools: the Pro Tools layout takes over. Repeat Record, Undo, Zoom.
- [ ] Right-hand layout: same checks with the mirrored keys.
- [ ] A foot pedal or controller button sending F18 toggles one-hand mode once per press, even
      when held.
- [ ] Lock the screen with ⌘ held (Ctrl+⌘+Q), unlock: one-hand keys still work.

#### Limitless Voice (needs a mic; Logic and/or Pro Tools)
- [ ] First launch asks for **Microphone**, then **Accessibility**. The level meter moves when he talks.
- [ ] Built-in mic, then a USB mic or headset if he has one: switching mics in settings works
      without restarting.
- [ ] In Logic, in a normal speaking voice from where he sits: "record", "stop", "undo", "go to
      bar thirty two", "show the mixer", "solo the track", "zoom in". Count how many of 20 tries
      work first time.
- [ ] Same with music playing from the speakers at a normal level. Count again.
- [ ] Say "go to sleep", then talk normally for a minute: nothing happens. "Wake up" works.
- [ ] Talk to someone in the room for two minutes without saying commands: count anything that fires.
- [ ] Say "delete fifty times" with a region selected (save the project first): it deletes at
      most 3 things. (Fixed on PR #1; confirm.)
- [ ] Unplug the USB mic while it's listening, plug it back in: it recovers on its own.
- [ ] If he has a speech difference or a quiet voice, or knows someone who does: note accuracy honestly.
- [ ] Pro Tools: repeat the main commands.

#### Limitless Zoom (Logic, Pro Tools, any app)
- [ ] Permissions as asked. The panel appears and stays on top.
- [ ] **On an Apple silicon Mac:** press Zoom in on the panel, then turn on the zoom key layer.
      Zoom must keep running. (It used to quit on the first zoom: a macOS trap when the keyboard
      layout was read off the main thread.)
- [ ] In Logic and Pro Tools: zoom in, zoom out, fit, taller/shorter tracks from the panel, from
      the zoom key layer, and by voice if Voice is on.
- [ ] Dwell on a panel button with the mouse: it fires once after the dwell time, not again
      while the pointer rests.
- [ ] Outside a DAW, zoom in/out drives macOS screen zoom (turn on Accessibility → Zoom first if asked).
- [ ] Hold the switch key: one action per press.

#### Limitless Color (any screen)
- [ ] Turning screen colors on asks for **Screen Recording**; after allowing it (and toggling off
      and on as the app says), the whole screen is recolored.
- [ ] Move windows, scroll, play video: lag and flicker? The mouse pointer must never lag.
- [ ] Second display (if any) and switching Retina resolution: both stay correct.
- [ ] ⌘⌥C toggles from inside Logic. "Hold to compare" shows the original colors.
- [ ] Quick eye check runs and picks a starting correction.
- [ ] **Crash safety:** with colors on, Force Quit Limitless Color (⌘⌥Esc). The screen must go
      back to normal within a couple of seconds. If it stays recolored, that's a top-priority bug.
- [ ] Log out and back in with colors on: no stuck overlay.
- [ ] With the tuner open and nothing changing, Activity Monitor shows Limitless Color near 0% CPU.
      (It used to re-save its profile five times a second.)

#### Limitless Control (Xbox Adaptive Controller)
- [ ] Plug in by USB-C, then pair by Bluetooth: the app shows it connected both ways.
- [ ] With **Logic in front** (not the Control window), the big buttons do Play/Stop and Record.
      This is the biggest unknown: whether macOS gives controller input to a background app.
- [ ] A switch in each 3.5 mm jack: each does its mapped command once per press.
- [ ] Tap quickly, hold, and press with a shaky hand: no double fires, holds work.
- [ ] Hold a trigger or stick halfway with a shaky hand: it must not fire over and over. (Fixed in
      0.2.1; confirm.) Try the "Some tremor" and "Strong tremor" timing presets too.
- [ ] Pull the cable mid-press: nothing keeps repeating. Plug back in: it reconnects.
- [ ] The settings page opens and works with VoiceOver (⌘F5).

#### GazeStage (webcam; Pro Tools for the transport)
- [ ] First launch asks for **Camera** (and Microphone for sound selection). Guided setup runs.
- [ ] Head pointer: comfortable to reach every target? Note the range setting he prefers.
- [ ] Eye gaze after calibration: how close does the pointer land? With glasses, without, in low light.
- [ ] Dwell on note pads plays the built-in sound. Switch, long blink and "ta" selection each work.
- [ ] Look away from the screen mid-note: the note stops within about half a second.
- [ ] Hold a note with a switch and click into Pro Tools: the note stops and the switch still
      works afterwards. (Bug fixed in 0.3; confirm.)
- [ ] Pro Tools: add GazeStage as a HUI controller (README steps). Play and Record work. **Check
      rewind, fast forward and stop**: their codes are unconfirmed.
- [ ] Ten minutes of use: Activity Monitor memory stays roughly level, the fan stays reasonable.
- [ ] Frame rate feels smooth (the stress test printed it).

#### The whole suite together (hub)
- [ ] Open Limitless Sound: its page opens in the browser and lists the installed apps.
- [ ] Open all apps from the page. Each shows as connected.
- [ ] A controller button triggers zoom in (any input → any app).
- [ ] Press Record in Logic via any app: Voice switches to take mode and ignores talking until
      stop.
- [ ] One-hand mode on turns the zoom keys layer off, and the other way round.
- [ ] Open a second copy of an app (double-click it twice): the suite settles on one, no flicker.
- [ ] Spoken confirmations never talk over each other.
- [ ] Quit Zoom, then trigger zoom in from the page: it still works through Zoom's command line,
      and the rest of the suite doesn't freeze while it does.

### 5. Wrap up

Summarise `HANDOFF-RESULTS.md` for Bennet in a few lines: what works, what failed, what needs a
musician to try. Commit it on a branch named `results/<date>` and open a pull request, so the
app threads can pick up the failures.
