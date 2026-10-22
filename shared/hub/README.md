# Limitless Sound hub

The small background app that makes the Limitless Sound apps work as one suite. Standard
library Python only. See [`../PROTOCOL.md`](../PROTOCOL.md) for how apps talk to it.

## For musicians

Install **Limitless Sound** (Mac `.dmg`, Windows setup `.exe`) and open it once. A page opens in
your web browser with five sections:

- **My apps**: which Limitless Sound apps are installed and open; open them, choose which open
  together, and start Limitless Sound when you sign in.
- **Do anything**: try any action from any app, and copy a web address for any action to put
  on a Stream Deck button, in Shortcuts or in AutoHotkey.
- **Links**: "when this happens, do that" between apps, each one on or off. Built in: during a
  take Limitless Voice only listens for stop and wake words; one-hand mode and the zoom keys
  never fight.
- **Settings**: spoken feedback, one voice for every app, text size, high contrast, reduced
  motion, dwell time, scanning speed, and which app presses DAW keys first.
- **Activity**: what just happened, for checking a setup.

The page works with VoiceOver, NVDA, Narrator and JAWS and fully from the keyboard (arrow keys
move between sections). Limitless Sound keeps running when the page is closed; **Quit** is on
the **My apps** section.

## For developers

```sh
pip install pytest
python -m pytest -q                       # 45 tests; the JS and Rust client tests need node / cargo
python -m limitless_hub                   # run it
python -m limitless_hub do zoom.in        # run any action
python -m limitless_hub list              # every action in the suite
pyinstaller --noconfirm packaging/limitless_hub.spec
```

| File | Job |
|---|---|
| `bus.py` | The action bus: tools, actions, DAW intents, events, links, prefs. No sockets, fully tested. |
| `routes.py` | Sidechain links: matching, defaults, runaway protection. |
| `catalog.py` | The six apps: names, install locations, built-in actions, command-line fallbacks. |
| `server.py` | TCP for apps, HTTP for the page and `/do/` triggers, `link.json`. |
| `speech.py` | One voice: queue, duplicate filter, `hub.speaking`. |
| `launcher.py` | Find and open apps; start at sign-in (LaunchAgent, HKCU Run, XDG autostart). |
| `web/index.html` | The settings page. |
