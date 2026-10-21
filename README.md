# Limitless Sound

Music software that leaves no one behind. Limitless Sound is a suite of free, offline
tools that let musicians with disabilities make music in Logic Pro, Pro Tools, Ableton Live
and the rest of their computer, on an ordinary Mac or Windows PC with whatever microphone,
webcam, keyboard, switch or controller they already have.

| App | Folder | What it does |
|---|---|---|
| **Limitless Voice** | [`apps/voice`](apps/voice) | Voice commands for the DAW and the whole computer, fully offline. |
| **Limitless One-Hand** | [`apps/one-hand`](apps/one-hand) | Turns the keys under one hand into the DAW commands you use most. |
| **Limitless Zoom** | [`apps/zoom`](apps/zoom) | Zoom the DAW or the screen by voice, one hand, dwell or a single switch. |
| **Limitless Color** | [`apps/color`](apps/color) | Recolors the whole screen for colorblind musicians. |
| **Limitless Control** | [`apps/control`](apps/control) | Xbox Adaptive Controller, switches and gamepads as DAW key commands. |
| **GazeStage** | [`apps/gazestage`](apps/gazestage) | Play instruments and run the transport with your eyes, head, a sound or a switch. |
| **Limitless Sound hub** | [`shared/hub`](shared/hub) | Joins them into one suite (below). |

## One suite: any input can do anything

The apps feed each other the way a sidechain feeds a compressor. The small **Limitless Sound
hub** runs in the background and gives every app one shared action bus:

- **Any input triggers any app.** A controller button can zoom, a glance in GazeStage can
  switch the screen colors on, a spoken phrase can turn on one-hand mode.
- **Shared DAW intents.** Any app can ask for `daw.record`, `daw.undo`, `daw.zoomIn`...
  and whichever open app knows the keys for the DAW in front presses them. GazeStage, which
  can't press keys itself, gets the whole keyboard through the others.
- **Sidechain links.** "When this happens, do that", in plain language and switchable on
  the settings page. Built in: while recording, Limitless Voice only listens for stop and wake
  words, so singing in a take can't trigger commands; one-hand mode and the zoom keys layer
  never fight over the same keys.
- **One voice.** Spoken confirmations from every app go through one speaker, said once,
  never on top of each other, and Limitless Voice never hears them.
- **Shared accessibility settings.** Text size, high contrast, dwell time and scan speed
  set once for every app.
- **One launcher.** See which apps are installed and open, open them, start the suite at sign-in.
- **Triggers from outside:** `Limitless Sound do zoom.in` on the command line, or
  `http://127.0.0.1:47901/do/daw.record?t=<token>` from a Stream Deck, Shortcuts or AutoHotkey.

Every app still works exactly as before on its own. With no hub, the link does nothing.

How it works: [`shared/PROTOCOL.md`](shared/PROTOCOL.md). Client libraries for Python,
JavaScript and Rust are in [`shared/clients`](shared/clients).

## Repository layout

```
apps/<app>/                 one folder per app, self-contained (its own deps, tests, packaging)
shared/hub/                 the Limitless Sound hub (Python, standard library only)
shared/clients/             Limitless Link client for Python, JavaScript and Rust
.github/workflows/<app>.yml one workflow per app, filtered to its folder
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the conventions each app follows.

## Status

Nothing here is signed yet: macOS asks you to choose **Open Anyway** and Windows SmartScreen
asks for **More info > Run anyway** the first time. Signing needs an Apple Developer ID and
a Windows code-signing certificate. Each app's README lists what has and hasn't been tested
on real hardware.
