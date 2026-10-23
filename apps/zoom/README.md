# Limitless Zoom

Part of **Limitless Sound**: music software that leaves no one behind.

Limitless Zoom lets a musician zoom their DAW, or the whole screen, without
needing a mouse or two hands. It runs on **macOS 12+ (Apple Silicon and Intel)**
and **Windows 10 and 11**, with any microphone the computer can see. Voice
recognition is fully offline: no internet, no account, audio never leaves the computer.
Linux works too, for testing.

## Ways to zoom

| Way | How |
|---|---|
| **Voice** | Say "zoom in", "zoom out", "zoom way in", "taller", "shorter", "fit", "show everything", "magnifier", "magnify", "preset one"…"preset five", "again". "Stop listening" pauses it; "start listening" brings it back. |
| **One hand** | Tap **Right Option** on a Mac (Right Ctrl on Windows, or any key you choose) to turn the zoom keys on. A yellow "ZOOM KEYS ON" badge shows. Then: **E** in, **Q** out, **S** taller, **W** shorter, **A** fit, **R/F** in/out a lot, **Z** magnifier, **X/C** magnify more/less, **1–5** presets. Hold a key to keep zooming. Tap the zoom key again, or Escape, to turn them off. Shortcuts with Cmd/Ctrl/Alt still work as normal while it's on. |
| **Eyes, head pointer, trackball** | A floating panel of big buttons. Rest the pointer on one for under a second and it presses; keep resting to keep zooming. It never takes focus away from the DAW. |
| **One switch** | Press your switch (you choose its key on first run) to start scanning. Buttons light up one at a time; press again to pick the lit one. |
| **Other tools** | `"Limitless Zoom" --do in` (or any action name) tells the running app to act, so Voice Control, Stream Deck, Shortcuts or other Limitless Sound tools can drive it. |

Every action is shown in large text and spoken aloud (turn speech off in the menu).

Waiting costs almost nothing: the speech recognizer only runs while the microphone hears
something, from a second before a sound to a second and a half after it, and nothing on
screen redraws while nothing changes.

## What gets zoomed

The app looks at which program is in front and presses that program's own zoom keys:

| | Logic Pro / GarageBand | Pro Tools (Mac / Windows) | Ableton Live | Anything else |
|---|---|---|---|---|
| Zoom in / out | Cmd+→ / Cmd+← | Cmd+] / Cmd+[ · Ctrl+] / Ctrl+[ | + / − | Screen magnifier |
| Taller / shorter tracks | Cmd+↓ / Cmd+↑ | Ctrl+↓/↑ · Start+↓/↑ | | |
| Fit | Z (Logic) | Option+A · Alt+A | Z | |
| Waveform bigger / smaller | | Option+Cmd+] / [ · Ctrl+Alt+] / [ | | |
| Zoom presets 1–5 | | Ctrl+1–5 · Start+1–5 | | |

Screen magnifier: macOS Zoom (Option+Cmd+8 / = / −) or Windows Magnifier (Win+Plus / Win+Minus / Win+Esc).

These are the factory key commands. If a DAW has been remapped, change them in
`settings.json` under `key_overrides` (see `limitless_zoom/keymaps.py`).

## Installing

Download the installer for your computer from the project's Releases page (or the
build's artifacts): `Limitless-Zoom-mac-apple-silicon.dmg` for M1/M2/M3/M4 Macs,
`Limitless-Zoom-mac-intel.dmg` for Intel Macs, `Limitless-Zoom-Setup-windows.exe` for Windows.

**Mac** (macOS 12 or newer)
1. Open the `.dmg` and drag Limitless Zoom onto Applications.
2. Double-click it in Applications. It isn't signed by Apple yet, so the first time
   macOS may refuse. Go to System Settings > Privacy & Security, click **Open Anyway**
   next to Limitless Zoom, and confirm. This is needed only once.
3. The setup window opens. Click **Allow…** next to Accessibility, Input Monitoring and
   Microphone. Each turns into a green tick the moment it's allowed, and the zoom keys
   start working straight away with no restart. Optionally turn on Accessibility > Zoom >
   "Use keyboard shortcuts to zoom" for whole-screen zoom.
4. Tap **Right Option** and press E, or say "zoom in". The setup window shows what
   it heard and a live microphone meter.

The app lives in the menu bar (magnifier icon): voice on/off, microphone, your keys,
Open at login, and Setup.

**Windows:** run `Limitless-Zoom-Setup-windows.exe`. If SmartScreen warns, choose
More info > Run anyway (it isn't signed yet). The zoom key is a tap of **Right Ctrl**.
If Pro Tools runs as administrator, run Limitless Zoom as administrator too.

## Settings file

- Mac: `~/Library/Application Support/Limitless Zoom/settings.json`
- Windows: `%APPDATA%\Limitless Zoom\settings.json`

Useful ones: `dwell_ms` (dwell time), `scan_ms` (scan speed), `button_scale` (button size),
`voice_confidence` (raise it if music sets off commands), `big_steps`.

## For developers

```
pip install -r requirements.txt pytest pyinstaller
QT_QPA_PLATFORM=offscreen python -m pytest      # 31 tests
python -m limitless_zoom                        # run from source
pyinstaller packaging/limitless_zoom.spec       # build the app for this OS
```

GitHub Actions (`.github/workflows/zoom.yml` at the repo root) builds the Mac (Apple Silicon and Intel)
and Windows installers on every push, runs the tests, checks voice recognition with
recorded speech, and publishes a `zoom-v<version>` release when a new version in
`limitless_zoom/__init__.py` reaches `main`.

Layout: `actions.py` (actions and phrases), `keymaps.py` (per-app keys), `router.py`
(action → keys), `hotkeys.py` (zoom key layer and switch), `voice.py` (offline speech),
`ui.py` (panel, toasts, welcome), `platforms.py` (per-OS code), `app.py` (wiring, tray).

## Known gaps

- Not yet tried on a real Mac or Windows PC; Linux is tested. The first Mac and Windows builds need hands-on testing.
- Not code-signed. Signing needs an Apple Developer ID ($99/year) and a Windows code-signing certificate.
- Pro Tools Windows Start-key shortcuts (track height, presets) may be caught by Windows itself; needs checking.
- Voice commands are English only for now, even when Zoom's windows are in Spanish; Vosk has models
  for 20+ languages, but each needs its phrases measured with real speech.

## Works with the rest of Limitless Sound

When the Limitless Sound hub is running, Zoom joins the suite by itself:

- Any other app can zoom: a controller button, a glance in GazeStage, a voice command, a
  Stream Deck button. Every zoom action is available, plus "zoom keys on" and "zoom keys off".
- Zoom answers the suite's shared zoom requests (zoom in, zoom out, fit) for the app in front.
- When the zoom keys layer turns on, the suite turns one-hand mode off, and the other way
  round, so the two never fight over the same keys.
- The panel follows the suite's shared dwell time and scanning speed, and spoken feedback goes
  through the suite's one voice when that setting is on.
- Every window (the panel, the big-text messages, the "ZOOM KEYS ON" badge, setup) follows the
  suite's text size, high contrast and reduced motion settings straight away, with no restart.
  If the panel's own `button_scale` makes its text bigger, the bigger one wins. With reduced
  motion the dwell bar fills in steps instead of sliding, and menus and tooltips don't animate.
  Zoom tells the suite which of these settings it's using (Limitless Access Standard level 2,
  Adaptive).
- Zoom's windows, menu and spoken messages are in the language picked in Limitless Sound, English
  or Spanish, or the computer's language until the hub is running. A new choice shows straight away.

Without the hub nothing changes. The link is `limitless_zoom/suite.py`, using a copy of
`shared/clients/python/limitless_link.py`.
