# GazeStage

GazeStage lets you play virtual instruments and run the Pro Tools transport using your head, your eyes, a sound into the microphone, or any switch. It runs completely offline. Video and audio never leave the computer, and nothing is recorded.

## What you need

- **A computer:** a Mac with macOS 12 or newer (Apple Silicon or Intel), or a Windows 10 or 11 PC (64-bit). Anything from about 2017 onward should be fast enough.
- **A webcam:** the built-in camera or any USB webcam. 720p is enough. Face the light, not a bright window.
- **A microphone (optional):** the built-in mic or any USB or headset mic. You only need it if you want to use a sound as the switch.
- **A switch (optional):** anything that types a key. That includes an adaptive switch interface, a foot pedal, a big-button keyboard, or an Xbox Adaptive Controller with a key-mapping tool.

## Download and install

Get the installer from the newest `gazestage-v…` release on the repository's Releases page.

| Computer | File |
| --- | --- |
| Mac with Apple Silicon (M1 or later) | `GazeStage-<version>-mac-arm64.dmg` |
| Mac with Intel | `GazeStage-<version>-mac-x64.dmg` |
| Windows PC | `GazeStage-<version>-win-x64.exe` |

**Mac:** Open the .dmg file and drag GazeStage to Applications. The first time, macOS will say it can't check the developer. Open System Settings > Privacy & Security, scroll down and click **Open Anyway**. When asked, allow the camera, and the microphone too if you want sound control.

**Windows:** Run the installer. If SmartScreen appears, click **More info > Run anyway**.

These warnings appear because this test build isn't signed with a paid developer certificate yet.

## First run

1. Click **Start camera**. Sit about an arm's length from the screen with your face centred.
2. Click **Calibrate** and follow the red dots. In head mode, point your nose at each dot. In eye mode, keep your head still and look at each dot.
3. Choose how to select:
   - **Dwell:** look at a target and hold. You can set the hold time from 0.25 to 2.5 seconds.
   - **Switch:** press any key.
   - **Long blink:** close both eyes for about a third of a second.
   - **Sound:** make a short pop, click or "ta" into the mic. Use **Mic sensitivity** if it fires too easily or not easily enough.
4. Open **Play an instrument** and try the pads. If no MIDI is set up yet, you'll hear the built-in sound.
5. Turn on **Keep on top** so GazeStage stays visible above Pro Tools or your DAW.

## Connecting to Pro Tools and instruments

GazeStage sends MIDI through virtual MIDI ports. You need three of them:

| Port name | Used for |
| --- | --- |
| To Pro Tools | Transport button presses going to Pro Tools |
| From Pro Tools | Pro Tools' "are you there" check coming back |
| GazeStage Notes | Notes for instruments |

**Mac:** open Audio MIDI Setup and choose Window > Show MIDI Studio. Double-click **IAC Driver**, tick "Device is online", and add the three ports with the names above.

**Windows 11:** open the **MIDI Settings** app that comes with Windows MIDI Services and add loopback endpoints with the names above. On Windows 10, or if you don't have that app, install the free **loopMIDI** by Tobias Erichsen and create the three ports there.

**Pro Tools (Mac or Windows):**

1. Go to Setup > Peripherals > MIDI Controllers.
2. Add a **HUI** with Receive From set to "To Pro Tools" and Send To set to "From Pro Tools".
3. In GazeStage, set **Pro Tools out** to "To Pro Tools" and **Pro Tools in** to "From Pro Tools". The footer should then say "Pro Tools link: connected".

**Instruments:** in GazeStage, set **Instrument out** to "GazeStage Notes". Then set the MIDI input of an instrument track (or any standalone synth) to that port and record-enable or input-monitor it. The same setup works in other DAWs that support HUI, such as Logic, Cubase and Reaper.

## Known limits in 0.2.0

- It hasn't been tested yet with a real face on camera, a real Pro Tools rig, or a player. The automated tests only checked that the app starts, loads the face model offline, and opens the camera, microphone and MIDI.
- The HUI codes for rewind, fast forward and stop haven't been confirmed. If one of those buttons does the wrong thing, tell us which.
- GazeStage only controls its own window. Moving the real mouse cursor and sending keyboard shortcuts to Pro Tools is planned next.

## For developers

```sh
npm install              # also fetches the MediaPipe runtime and face model into renderer/vendor
npm start                # run the app
npm test                 # smoke test (on Linux: xvfb-run -a npm test)
npm run dist:mac-arm64   # or dist:mac-x64 / dist:win / dist:linux; output in dist/
npm run test:packaged    # smoke test the built app in dist/
```

The app is a small Electron shell (`main.js`) around one page (`renderer/index.html`). The page is served from `app://`, so the camera, microphone and Web MIDI behave the same on every platform. CI (`.github/workflows/gazestage.yml`) tests every pull request and builds the Mac .dmg files and the Windows installer. A `gazestage-v*` tag attaches them to a release.
