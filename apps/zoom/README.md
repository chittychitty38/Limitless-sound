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
| **One hand** | Tap your zoom key once (you choose it on first run) to turn the zoom keys on. A yellow "ZOOM KEYS ON" badge shows. Then: **E** in, **Q** out, **S** taller, **W** shorter, **A** fit, **R/F** in/out a lot, **Z** magnifier, **X/C** magnify more/less, **1–5** presets. Hold a key to keep zooming. Tap the zoom key again, or Escape, to turn them off. Shortcuts with Cmd/Ctrl/Alt still work as normal while it's on. |
| **Eyes, head pointer, trackball** | A floating panel of big buttons. Rest the pointer on one for under a second and it presses; keep resting to keep zooming. It never takes focus away from the DAW. |
| **One switch** | Press your switch (you choose its key on first run) to start scanning. Buttons light up one at a time; press again to pick the lit one. |
| **Other tools** | `"Limitless Zoom" --do in` (or any action name) tells the running app to act, so Voice Control, Stream Deck, Shortcuts or other Limitless Sound tools can drive it. |

Every action is shown in large text and spoken aloud (turn speech off in the menu).

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

Download the installer for your computer from the project's Releases page.

**Mac:** open the `.dmg` and drag Limitless Zoom to Applications. The first time,
right-click it and choose Open (it isn't signed by Apple yet). macOS will ask for:
- **Accessibility** and **Input Monitoring** (System Settings > Privacy & Security), so it can press zoom keys and hear your zoom key.
- **Microphone**, for voice commands.
- For whole-screen zoom, switch on System Settings > Accessibility > Zoom > "Use keyboard shortcuts to zoom".

**Windows:** run `Limitless-Zoom-Setup-windows.exe`. If SmartScreen warns, choose
More info > Run anyway (it isn't signed yet). You can tick "Start when I sign in".
If Pro Tools runs as administrator, run Limitless Zoom as administrator too.

The app lives in the menu bar (Mac) or system tray (Windows). Its menu has voice on/off,
microphone choice, speech on/off, and choosing your zoom and switch keys.

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
recorded speech, and attaches installers to a release when a `zoom-v*` tag is pushed.

Layout: `actions.py` (actions and phrases), `keymaps.py` (per-app keys), `router.py`
(action → keys), `hotkeys.py` (zoom key layer and switch), `voice.py` (offline speech),
`ui.py` (panel, toasts, welcome), `platforms.py` (per-OS code), `app.py` (wiring, tray).

## Known gaps

- Not yet tried on a real Mac or Windows PC; Linux is tested. The first Mac and Windows builds need hands-on testing.
- Not code-signed. Signing needs an Apple Developer ID ($99/year) and a Windows code-signing certificate.
- Pro Tools Windows Start-key shortcuts (track height, presets) may be caught by Windows itself; needs checking.
- Voice is English only for now; Vosk has models for 20+ languages.
