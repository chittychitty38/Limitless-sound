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
- **Tone:** an XY pad for shifting your sound hands-free. Left–right and down–up each send a MIDI controller, so one point moves two things at once: drive and delay, wah and mix, or any two controls on an amp, a Helix or a plugin. See [The tone pad](#the-tone-pad).
- **Pause:** look at Pause to rest. Nothing fires until you look at Resume.
- If the pointer drifts, choose **Recenter** (⌘R). **Calibrate** (⌘K) fits the pointer to you.

## The tone pad

Open **Tone** (⌘3). The yellow point is where your tone is.

- **Place it:** look anywhere on the pad and hold still. When the ring fills, the point glides there. With a switch, a sound or a long blink, it goes to the pointer straight away. A helper can click or drag.
- **Follow:** turn on **Follow** and the point follows you while you look around the pad, for live sweeps. It waits a moment when you first look onto the pad, so glancing across never moves your tone. With a switch, it follows only while you hold the switch.
- **Arrows:** step the point. Keep looking at an arrow to keep it moving.
- **A, B, C, D:** saved tones. Choose **Save here**, then a letter, to save where the point is now. Choosing a letter glides to that tone.
- **Glide:** how long a move takes, from instant to 4 seconds, for smooth tone morphs.
- **Listen:** holds a chord on the built-in sound so you can hear the pad work with nothing else connected. Left–right makes it darker or brighter, and up–down adds room.

**What it sends:** CC 16 (left–right) and CC 17 (down–up) on channel 1, 0 to 127. You can change the numbers, the channel and the names in Settings › Tone pad.

**A plugin in Pro Tools:** set the track's MIDI input to `GazeStage Notes`. Start MIDI learn on the plugin control, then in Settings › Tone pad choose **Teach left–right** or **Teach up–down**. Only that one controller moves, so the plugin learns the right one.

**A Line 6 Helix, HX Stomp or POD Go:** plug it in with USB. GazeStage finds it and sends to it automatically. In Settings › Tone pad › Controller numbers, choose **Line 6 Helix: EXP 1 and EXP 2 pedals**. GazeStage then sends CC 1 and CC 2, which the Helix treats as its EXP 1 and EXP 2 pedals. Anything you assign to those pedals on the Helix, such as a wah, a volume swell or a set of parameters, now follows the point. Other Limitless Sound apps can move the pad too, for example a voice command "tone A".

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
| ⌘1 / ⌘2 / ⌘3 | Transport / Instrument / Tone |
| ⌘. | All notes off |
| ⌘, | Settings |

## Display and Limitless Sound

Settings › Display has light or dark, high contrast, text size and the space between targets. GazeStage also follows your computer's reduce motion setting.

When Limitless Sound is running, GazeStage also follows the suite's shared text size, high contrast and reduced motion settings. It uses whichever is more accessible: the larger text, and high contrast or reduced motion if either one asks for it. Reduced motion turns off animations and fills the dwell ring in steps. It never changes when something is selected. Dwell and switch timing stay GazeStage's own, in Settings › Selecting.

GazeStage is in English or Spanish: the suite's language while Limitless Sound runs, otherwise your computer's. That covers the window, the guided setup, the menu and its answers to other apps. Pro Tools' own menu names and the MIDI port names stay in English, because that is how they appear in Pro Tools.

## Known limits

- It hasn't been tested yet on a real Pro Tools rig or with a player. The HUI codes for rewind (1), fast forward (2) and stop (3) are unconfirmed.
- The tone pad hasn't been tried on a real Helix yet. CC 1 and CC 2 as EXP 1 and EXP 2 come from Line 6's published MIDI table.
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
| `renderer/synth.js` | The built-in instrument. It plays in a hidden page and process of its own (`renderer/synth.html` and `synth-page.js`; `synth-link.js` is the window's side, `synth-preload.js` its bridge), because starting the computer's audio can hold up the page that starts it for seconds |
| `renderer/midi.js` | Native or Web MIDI routing and the HUI link |

CI (`.github/workflows/gazestage.yml`) runs the tests on every pull request. It then builds the Mac .dmg files and the Windows installer, smoke tests each built app, and checks that the macOS build creates its own MIDI ports. A `gazestage-v*` tag attaches the installers to a release.
