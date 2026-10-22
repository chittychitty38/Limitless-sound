# Limitless Sound

**Music is for every body.** Free, offline music software that lets musicians with disabilities
play, record and mix in Logic Pro, Pro Tools, Ableton Live and the rest of their computer, on an
ordinary Mac or Windows PC, with their voice, one hand, their eyes, a single switch, a foot pedal
or an adaptive controller. From the [Limitless Sound Foundation](https://chittychitty38.github.io/Limitless-sound/).

## Get it

| Your computer | Download |
|---|---|
| Mac with Apple silicon (M1 and newer) | [Limitless-Sound-Suite-mac-apple-silicon.pkg](https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-apple-silicon.pkg) |
| Mac with Intel | [Limitless-Sound-Suite-mac-intel.pkg](https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-mac-intel.pkg) |
| Windows 10 or 11 | [Limitless-Sound-Suite-windows.exe](https://github.com/chittychitty38/Limitless-sound/releases/latest/download/Limitless-Sound-Suite-windows.exe) |

One installer puts every app on your computer. Then Limitless Sound asks two questions, **how do
you like to play?** and **how should things look and sound?**, opens the apps that fit you, and
sets the text size, contrast and motion every app follows. Change it any time.

The apps aren't signed with a paid certificate yet, so the first time, macOS asks you to click
**Open Anyway** (System Settings › Privacy & Security) and Windows asks for **More info › Run anyway**.

## The apps

| App | What it does |
|---|---|
| [**Limitless Voice**](apps/voice) | Voice commands for the DAW and the whole computer, fully offline. |
| [**Limitless One-Hand**](apps/one-hand) | The keys under one hand become the DAW commands you use most. |
| [**Limitless Zoom**](apps/zoom) | Zoom the DAW or the screen by voice, one hand, dwell or a single switch. |
| [**Limitless Color**](apps/color) | Recolors the whole screen for colorblind musicians. |
| [**Limitless Control**](apps/control) | The Xbox Adaptive Controller, switches and gamepads as DAW commands. |
| [**GazeStage**](apps/gazestage) | Play instruments and run the transport with your eyes, head, a sound or a switch. |
| [**Limitless Sound**](shared/hub) | Joins them, so any input can do anything. |

All six meet **level 2 (Adaptive)** of the [Limitless Access Standard](standard): set your text
size, contrast and motion once, and every app follows, live.

### One suite: any input can do anything

- **Any input triggers any app.** A controller button can zoom; a glance in GazeStage can press
  Record; a spoken phrase can turn on one-hand mode.
- **Shared DAW commands.** Any app can ask for `daw.record`, `daw.undo`, `daw.zoomIn`..., and
  whichever open app knows the keys for the DAW in front presses them.
- **Links between apps**, in plain language: while recording, Voice only listens for "stop", so
  singing in a take can't trigger commands; one-hand mode and Zoom's keys never fight.
- **One voice.** Spoken confirmations from every app take turns and never talk over each other.
- **From anywhere:** `Limitless Sound do zoom.in` on the command line, or a URL from a Stream Deck,
  Shortcuts or AutoHotkey.

Every app also works on its own, exactly the same without the others.

## Proven every night

Every night a fresh Apple silicon Mac, a fresh Intel Mac and a fresh Windows PC download the
suite from the links above, install it, open every app and run the Access Standard test kit
against each one: it must join the suite, answer every one of its commands within three
seconds, keep running, be ready in seconds and sit quietly when idle. The results, failures
included, are on the [website](https://chittychitty38.github.io/Limitless-sound/#proof), and
every app crash comes with its macOS or Windows crash report in the [run's log](.github/workflows/proof.yml).

Those computers have no microphone, camera, controller or DAW, so musicians test the rest by
hand: [HANDOFF.md](HANDOFF.md) is the checklist. Each app's README says what has and hasn't been
tried on real hardware.

## For makers: the Limitless Access Standard

MIDI let any keyboard play any synth. The [Limitless Access Standard](standard) does the same for
access: a musician sets up their access once, and every instrument, plug-in, amp modeler or
recording app that carries the mark already fits them. It's open and free, built on the
[Limitless Link protocol](shared/PROTOCOL.md): JSON over a local socket, with ready clients for
[Python, JavaScript and Rust](shared/clients).

```sh
# Test your product against the standard (Python 3.10+, nothing to install):
python3 standard/conformance/las_check.py --tool myplugin --try-all --level adaptive
```

## Working on it

```
apps/<app>/                 one folder per app, self-contained (its own dependencies, tests, packaging)
shared/hub/                 Limitless Sound, the hub (Python, standard library only)
shared/clients/             Limitless Link clients, plus the app log and Mac keyboard helpers
standard/                   the Limitless Access Standard and its test kit
packaging/                  the suite installers (Mac .pkg, Windows .exe) and the nightly proof
docs/                       the website
.github/workflows/          one workflow per app, the suite, the stress tests and the proof
```

Each app releases itself when a new version reaches `main`; the suite releases when
`packaging/VERSION` changes. See [CONTRIBUTING.md](CONTRIBUTING.md) for the conventions each app
follows.
