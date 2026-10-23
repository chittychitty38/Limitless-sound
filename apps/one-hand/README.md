# Limitless One-Hand

Part of **Limitless Sound**: music software that leaves no one out.

Limitless One-Hand lets you run Logic Pro, Pro Tools, GarageBand, REAPER and FL Studio with one hand. Switch on one-hand mode and the keys under your hand become the DAW commands you use most: play, record, undo, split, mute, solo, zoom, save. Switch it off and your keyboard is normal again.

![](docs/screenshot.png)

## Works on

- **macOS 12 or later**, Apple Silicon and Intel: Logic Pro, Pro Tools, GarageBand 10, REAPER 7 and FL Studio
- **Windows 10 and 11**: Pro Tools, REAPER 7 and FL Studio

GarageBand, REAPER and FL Studio get only the keys their makers' guides give
([apps/voice/DAW-SHORTCUTS.md](../voice/DAW-SHORTCUTS.md)), so they have fewer commands than Logic
and Pro Tools. In FL Studio, E switches record mode (Space then plays and records), Q undoes one
step back through the history, and single keys only work while its "Typing keyboard to piano" is off.

Any keyboard works. Nothing else to install.

## Get it

Download the newest `one-hand-v…` release from the repository's **Releases** page:

- Mac: `Limitless-One-Hand-mac-apple-silicon.dmg` (M1 and newer) or `-mac-intel.dmg`. Open it and drag the app into Applications.
- Windows: `Limitless-One-Hand-windows.exe`. Double-click it to install; it adds Limitless One-Hand to the Start menu.

### First time on a Mac

1. Open the `.dmg` and drag **Limitless One-Hand** onto **Applications**.
2. Double-click it in Applications. It isn't signed by Apple yet, so macOS may say it can't check the app. Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway**. You only do this once. (The disk image includes these steps in *How to open One-Hand.txt*.)
3. A welcome page walks you through the two switches macOS needs, **Accessibility** and **Input Monitoring**. Each step has a button that opens the right page in System Settings, and the welcome page notices on its own when they're on.

### First time on Windows

Windows may show "Windows protected your PC" because the app is new. Choose **More info → Run anyway**.

## Using it

- **Switch on or off:** click the big button, **double-tap Shift** (either side), or press **F18**. F18 is for a foot pedal, Stream Deck, Xbox Adaptive Controller, or any switch that can send a key. On Windows you can also choose Caps Lock.
- **Pick your hand:** Left hand or Right hand. The right-hand layout is the mirror image, so each finger does the same job.
- **Space still plays and stops.** Hold Space and press a key to type the letter from the other half of the keyboard, handy for naming tracks. (Space now acts when you let go.)
- Real shortcuts still work: if you hold ⌘/Ctrl, Option/Alt or Shift, keys pass straight through.
- Keys only change while one of those DAWs is in front. Every other app types normally.
- **Try it here:** with one-hand mode on, press keys while the One-Hand window is in front. Each key's card lights up and tells you what it would do, without pressing anything.
- **Menu bar:** One-Hand keeps running in the menu bar (the 1H key) when you close its window. Click the icon to switch the mode or the hand, or to quit.
- **ON badge:** a yellow badge at the top of the screen shows when one-hand mode is on, even over a full-screen DAW.
- Options: sounds, spoken "on/off", larger text, keep the window on top, start with the mode on, and open at login. VoiceOver reads out each change.
- **Limitless Sound settings:** with the Limitless Sound hub running, the window and the ON badge follow the text size, high contrast and reduce motion you set once for the whole suite, the moment you change them. If One-Hand's own Larger text is bigger, it keeps that. High contrast makes everything pure black with white text and edges; reduce motion keeps the key you pressed lit instead of flashing it, and stops menus and lists sliding or fading.
- **English or Spanish:** the window, menu, badge, key names and spoken "on/off" are in the language you pick in Limitless Sound, or your computer's language until the hub is running. Pick another and they change straight away.
- Works alongside on-screen keyboards, Switch Control, Voice Control and other assistive tools: keys they type go through one-hand mode too.

For two-key shortcuts one finger at a time, also turn on Sticky Keys (Mac: Accessibility → Keyboard; Windows: Settings → Accessibility → Keyboard).

## Changing the commands

Copy `onehand/layouts.json` into the settings folder and edit it, then restart the app:

- Mac: `~/Library/Application Support/Limitless One-Hand/layouts.json`
- Windows: `%APPDATA%\Limitless One-Hand\layouts.json`

Keys are written for the left hand; the right-hand layout is worked out for you. Modifiers use Mac names (command, option, control, shift) and become Ctrl, Alt, Win and Shift on Windows. To add another app, add an entry with its Mac bundle ID and/or Windows program name (for example `Ableton Live 12 Suite.exe`).

## For developers

```sh
pip install -r requirements.txt pytest
python -m pytest           # engine tests
python main.py             # run the app
python main.py --self-test # load the keyboard code and check the hook
pyinstaller onehand.spec   # build the app for this system
```

`onehand/engine.py` holds all the remapping logic and has no system calls. `platform_mac.py` (Quartz event tap) and `platform_win.py` (low-level keyboard hook) feed it key events and carry out what it returns. `.github/workflows/one-hand.yml` (at the repository root) builds the Mac disk images and the Windows installer for every change to this folder, and attaches them to a release when a `one-hand-v*` tag is pushed.

## Known limits

- Not yet signed with an Apple Developer ID or a Windows code-signing certificate, so first launch shows a warning.
- Shortcuts are the DAWs' factory defaults; if you changed yours, edit the layout.
- Password fields block all keyboard tools on macOS, so one-hand mode pauses there.
