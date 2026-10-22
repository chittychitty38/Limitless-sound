# GazeStage

Play music and run Pro Tools with your head, your eyes, a short sound or a switch. GazeStage runs entirely on your computer. Video and audio never leave it, and nothing is recorded.

## What you need

- **A Mac** with macOS 12 or newer, Apple Silicon or Intel. Windows 10 and 11 are supported too.
- **A camera:** the built-in camera or any USB webcam. Face a light, not a bright window.
- **Optional:** a microphone (to select with a sound), or any switch that types a key (an adaptive switch, a foot pedal, or an Xbox Adaptive Controller with a key mapper).

## Install

Download from the newest `gazestage-v…` release on the Releases page.

| Computer | File |
| --- | --- |
| Mac with Apple Silicon (M1 or later) | `GazeStage-<version>-mac-arm64.dmg` |
| Mac with Intel | `GazeStage-<version>-mac-x64.dmg` |
| Windows PC | `GazeStage-<version>-win-x64.exe` |

**Mac:** Open the .dmg and drag GazeStage to Applications, then open it. The first time, macOS says it can't check the developer. Go to System Settings › Privacy & Security, scroll down, and click **Open Anyway**. This happens once, because the app isn't signed with a paid Apple developer certificate yet.

**Windows:** Run the installer. If SmartScreen appears, click **More info › Run anyway**.

## First launch

A short guided setup, about two minutes, walks you through five steps:

1. **Camera:** turns the camera on and checks that your face is found, the light is good, and you're centred at a good distance.
2. **Pointing:** use your head (recommended, works right away), your eyes (after a short calibration), or a mouse or other pointer, such as a head mouse or the macOS Head Pointer.
3. **Selecting:** look and hold (dwell), a switch or key, a short sound like a pop, click or "ta", or a long blink. Each option has a live test.
4. **Practice:** three targets to try. GazeStage centres itself on where you're looking first.
5. **Pro Tools:** the one-time connection steps.

A helper can click through setup with a mouse. Once the camera is on, every step can also be selected by pointing.

## Playing

- **Instrument:** big note pads in any key and scale. Higher notes are on the top row. **Chords** turns every pad into a chord that fits the key, and **Hold notes** latches notes on. The built-in sound has two voices, Soft keys and Warm pad, so it plays with no other software.
- **Transport:** Rewind, Play, Fast forward, Record and Stop for Pro Tools. Play and Record light up to match Pro Tools.
- **Pause:** look at Pause to rest. Nothing fires until you look at Resume.
- If the pointer drifts, choose **Recenter** (⌘R). **Calibrate** (⌘K) fits the pointer to you.

## Connecting Pro Tools (one time)

**Mac:** GazeStage creates its own MIDI ports, so there's nothing to install.

1. In Pro Tools, choose **Setup › Peripherals › MIDI Controllers**.
2. Add a **HUI** with **Receive From** and **Send To** both set to `GazeStage HUI`.
3. For instruments, set an instrument track's MIDI input to `GazeStage Notes`, then record-enable it. In Settings, turn off **Play the built-in sound** so you only hear Pro Tools.

**Windows:** create three loopback ports named `To Pro Tools`, `From Pro Tools` and `GazeStage Notes`. On Windows 11 use the MIDI Settings app. On Windows 10 use the free loopMIDI. GazeStage picks the ports up by name. Then in Pro Tools, add a HUI that receives from `To Pro Tools` and sends to `From Pro Tools`.

Other DAWs that support HUI work the same way, including Logic, Cubase and Reaper.

## Keyboard shortcuts (Mac)

| Shortcut | Action |
| --- | --- |
| ⌘R | Recenter the pointer |
| ⌘K | Calibrate |
| ⌘P | Pause or resume |
| ⌘1 / ⌘2 | Transport / Instrument |
| ⌘. | All notes off |
| ⌘, | Settings |

## Known limits

- It hasn't been tested yet on a real Pro Tools rig or with a player. The HUI codes for rewind (1), fast forward (2) and stop (3) are unconfirmed.
- GazeStage controls its own window. Moving the system cursor and sending shortcuts to other apps is planned through the Limitless Sound hub.

## For developers

```sh
npm install              # also fetches the MediaPipe runtime and face model into renderer/vendor
npm start                # run the app
npm test                 # unit tests, then the end-to-end smoke test (on Linux: xvfb-run -a npm test)
npm run dist:mac-arm64   # or dist:mac-x64 / dist:win / dist:linux; output in dist/
npm run test:packaged    # smoke test the built app in dist/
```

| Path | What it holds |
| --- | --- |
| `main.js` | Electron shell: the `app://` protocol, virtual MIDI ports (`@julusian/midi`), the menu, window state, and camera and microphone permissions |
| `preload.js` | The small bridge the page can use |
| `renderer/app.js` | Pointer, sticky targeting, selection, pages, guided setup and settings |
| `renderer/tracker.js` | The camera, and face and iris samples for the pointer |
| `renderer/face-worker.js` | MediaPipe face tracking, in its own thread so the window never freezes while it loads or works. It runs on the graphics chip or the CPU, whichever is faster on this computer, and says which (`gaze.faceTracking`) |
| `renderer/lib.js` | Pure logic covered by the unit tests: filter, calibration fit, head mapping, scales and chords, the HUI protocol, sound onsets |
| `renderer/synth.js` | The built-in instrument |
| `renderer/midi.js` | Native or Web MIDI routing and the HUI link |

CI (`.github/workflows/gazestage.yml`) runs the tests on every pull request. It then builds the Mac .dmg files and the Windows installer, smoke tests each built app, and checks that the macOS build creates its own MIDI ports. A `gazestage-v*` tag attaches the installers to a release.
