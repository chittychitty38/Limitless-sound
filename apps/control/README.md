# Limitless Control

Play, record and mix with an **Xbox Adaptive Controller**, accessibility switches, or any
gamepad. Each switch becomes a key command for Logic Pro, Pro Tools, Ableton Live or the rest
of your computer. Part of **Limitless Sound**: music technology with no one left behind.

**Runs on:** Mac (Apple silicon and Intel), Windows 10 and 11, and Linux (X11).
**For musicians:** see [INSTALL.md](INSTALL.md). It covers install, setup and the default buttons in plain language.

## What it does

- **Follows the app in front.** Built-in profiles for Logic Pro, Pro Tools and Ableton Live,
  plus an "Everyday" profile for everything else. It switches profiles automatically and
  says the name out loud.
- **Every input counts.** Buttons, all the 3.5 mm switch jacks, triggers and stick directions.
- **Layer switch.** One switch gives the next switch a second job (like Sticky Keys), so
  one hand gets twice the commands.
- **On/off switch.** Hold Menu to turn the controller off and on again, so you can rest
  on it or hand the computer to someone else.
- **Tap or hold.** Record sits on a *hold* of the big B button so it never starts by accident.
- **Hold to repeat** for zoom, scrolling and moving between tracks.
- **Tremor and double-hit filtering** that each musician can adjust.
- **Spoken confirmations** ("Record", "Mute", "Layer 2") that can be turned off.
- **Settings page** opens in the web browser, so VoiceOver, Narrator, NVDA, zoom and
  high-contrast modes all work. Press a switch and its row lights up; pick what it does
  from a list of named actions. Nobody edits files or uses a terminal.

## How it's built

| Part | File | Notes |
|---|---|---|
| Mapping engine | `limitless_control/engine.py` | Timing, layers, on/off, profiles. Pure Python, fully tested. |
| Controller input | `limitless_control/controller.py` | SDL2 game controller API (pygame-ce). Same button names on every system. Background input enabled. |
| Key output | `limitless_control/output.py` | pynput: Quartz on Mac, SendInput on Windows, X11 on Linux. Speech with `say`, SAPI or speech-dispatcher. |
| App in front | `limitless_control/frontmost.py` | Mac bundle ID, Windows program file name, Linux window class. |
| Profiles | `limitless_control/profiles.py` | Built-in actions per DAW and default layouts. `mod` means ⌘ on Mac and Ctrl on Windows. |
| Settings | `limitless_control/app.py`, `web/index.html` | Local web server on 127.0.0.1:47820. Requests need a per-launch token and a localhost Host header, so other websites can't change settings. |

User settings are saved to `~/Library/Application Support/Limitless Control/settings.json`
on Mac, `%APPDATA%\Limitless Control\settings.json` on Windows, and
`~/.config/Limitless Control/settings.json` on Linux.

## Developing

```
pip install -e ".[dev]"
pytest -q
python -m limitless_control --test-mode    # logs key commands instead of pressing them
```

## Building installers

`.github/workflows/control.yml` (repo root) runs the tests, then builds on GitHub's machines:

- `LimitlessControl-mac-apple-silicon.dmg` and `LimitlessControl-mac-intel.dmg`
- `LimitlessControl-<version>-Windows-Setup.exe` (Start menu entry and an optional "start when I sign in")
- `LimitlessControl-linux.tar.gz`

Every push makes downloadable builds under the run's Artifacts. Pushing a tag like `control-v0.1.0`
attaches them to a GitHub Release.

To build one locally: `pyinstaller packaging/limitless_control.spec`.

## Before a public release

- **Code signing.** Unsigned builds work, but Mac and Windows show a warning the first time
  you open them. Signing needs an Apple Developer ID (notarized) and a Windows code signing
  certificate.
- **Check the default shortcuts** on real installs of each DAW (see INSTALL.md, "Shortcuts to check").
- **Test with the musicians who will use it**, and tune the default timings to them.

## Roadmap

1. MIDI output so triggers and sticks can act as faders in any DAW.
2. Single-switch scanning: a spoken menu that steps through actions, chosen with one switch.
3. Shared actions with the voice control and eye tracking tools in Limitless Sound.
