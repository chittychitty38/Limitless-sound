# Limitless Voice

Control Logic Pro, Pro Tools, Ableton Live and the rest of your computer with your voice.
Built for musicians who can't use, or can't always use, a mouse and keyboard.

Say "go to bar thirty two", "solo track", "nudge right four times", "show the
mixer" or "press command shift N", and it happens in whatever app you're
working in. It runs entirely on your computer: no account, no internet once
installed, and your voice never leaves the machine.

## What it runs on

| | |
|---|---|
| **Mac** | macOS 11 (Big Sur) or newer. Apple Silicon (M1 and later) and Intel Macs each get their own download. |
| **Windows** | Windows 10 or 11, 64-bit. |
| **Microphone** | Any mic the computer already recognises: the built-in laptop mic, a USB mic, a headset, a webcam mic or an audio interface input. Any sample rate. A headset or a mic close to your mouth works best when speakers are playing. Bluetooth headsets work, but drop to phone-call quality, so expect more misses. |
| **Computer** | Anything from roughly the last ten years. Recognition uses about 300 MB of memory and a small share of one CPU core. About 300 MB of disk space. |
| **Language** | English (US) built in. A more accurate English model and an Indian English model can be downloaded from Settings. |
| **Apps** | Ready-made commands for Logic Pro (Mac), Pro Tools and Ableton Live 12 (Mac and Windows). Everything else works through the everyday commands (copy, undo, open apps, arrows...), "press ..." for any shortcut, and your own command files. |

Not covered yet: Linux, Chromebooks, iPad.

## Install

**Mac:** open the `.dmg`, drag Limitless Voice into Applications, open it.
A one-minute setup guide (spoken aloud as well as shown) walks through:
1. *Microphone*: press Allow microphone, then Allow in the macOS prompt.
2. *Control the computer* (Accessibility): press the button, turn on
   Limitless Voice in the list that opens, and come back. The guide notices
   by itself and moves on. This is what lets spoken commands press keys in
   Logic and Pro Tools.
3. *Mic check*: pick your mic and say "what can I say".
4. *How it answers you*: spoken replies, the on-screen display, larger text,
   high contrast, start at login.

Run it again any time from the menu bar icon > Run setup again.

**Windows:** run `LimitlessVoiceSetup.exe` and follow the steps. It installs
for your user only, so it doesn't need an administrator password. Windows may
ask about microphone access the first time; choose Allow.

> Until the downloads are signed with an Apple Developer ID and a Windows
> code-signing certificate, macOS says the app "can't be checked" and
> Windows SmartScreen says it's from an unknown publisher. On Mac:
> System Settings > Privacy & Security > Open Anyway. On Windows: More info >
> Run anyway.

## Using it

Open the app, click into Logic or Pro Tools, and talk. The window shows what
it heard and what it did, and it says the result out loud (you can turn that
off). It sends commands to the last app you were using, even if you've just
clicked on the Limitless Voice window.

| Say | What happens |
|---|---|
| "what can I say" | Lists every command for the app you're in |
| "go to sleep" / "wake up" | Stop and start listening, so talking or singing a take never triggers anything |
| "play", "record", "stop", "go to start" | Transport |
| "go to bar sixty four", "marker three" | Jump around (numbers just work, including "one twenty") |
| "solo track", "mute track", "arm track", "next track" | Tracks |
| "nudge right four times", "zoom in twice", "again" | Repeat things |
| "show the mixer", "piano roll", "midi editor" | Windows and views |
| "press command shift N" | Any shortcut. Letters can be said the pilot way: "press command shift november" |
| "open Pro Tools", "switch to Logic" | Apps |
| "begin dictation" ... "stop dictation" | Type what you say (track names, notes, lyrics), with "comma", "period", "new line", "scratch that" |

Built-in safety:
- "quit the app" and "close the window" ask you to say "yes" first.
- Record, delete, bounce and save-as only run on the exact words, never a
  near miss, so a lyric like "recorded" can't start a take.
- While the app is talking, it stops listening, so it never hears itself.

**While you work in Logic or Pro Tools** a small card at the bottom of the
screen shows what it heard and what it did, then fades. It never takes focus.
The menu bar icon shows the state at a glance: green listening, grey asleep,
red take mode, blue dictating. Closing the window keeps it listening from the
menu bar; choose Quit there to stop it.

**The window** works with VoiceOver, NVDA, Narrator and JAWS, and entirely by
keyboard (Ctrl+L, or Cmd+L on Mac, toggles listening). Settings has larger text, a
high-contrast theme, keep-on-top, speaking speed, and an optional keyboard
shortcut to toggle listening from anywhere (on Mac that shortcut needs the
Input Monitoring permission).

**Getting better accuracy:** pick your best mic in the Microphone menu and
watch the level bar move as you speak. Keep it closer than the speakers.
If commands get missed, try Settings > Speech model > "more accurate".

## Adding your own commands

"My commands folder" opens a folder for your own command files. There's a
how-to inside it. A command is a few lines:

```yaml
name: My Commands
apps: ["Pro Tools"]          # leave out for commands that work everywhere
commands:
  - say: ["drum bus", "show [the] drum bus"]
    do: {keys: cmd+shift+d}
```

- `[the]` is an optional word; `{bar:number}`, `{name:text}`,
  `{chord:keys}` and `{x:word}` are blanks the person fills in when speaking.
- Actions: `keys`, `type`, `open_app`, `wait`, `steps` (several in a row),
  `menu` and `applescript` (Mac only), `shell`.
- `confirm: true` asks before running; `fuzzy: false` needs the exact words;
  `repeatable: false` ignores "... times".
- Write shortcuts with Mac key names. On Windows `cmd` becomes Ctrl, `opt`
  becomes Alt and `ctrl` becomes the Windows key (the same mapping Avid uses
  for Pro Tools). Give a command `do_windows:` (written with Windows key names)
  when Windows needs something different, or `platforms: [mac]`.

The built-in commands live in `limitless_voice/packs/` and use each app's
**default** shortcuts. Lines marked "verify" are worth checking.

## Other ways to trigger commands

Every command can be run from outside the app, which lets macOS Voice
Control, Shortcuts, a Stream Deck, a foot pedal app or a switch interface
trigger it:

```
"/Applications/Limitless Voice.app/Contents/MacOS/Limitless Voice" do "go to bar 32"
"C:\Users\<you>\AppData\Local\Programs\Limitless Voice\LimitlessVoice.exe" do "solo track"
```

## For developers

```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
# get the model once (the app can also download it on first run)
mkdir -p models && curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
  && python -m zipfile -e vosk-model-small-en-us-0.15.zip models/
python run_app.py                       # the app
python run_app.py typed --dry-run --app "Pro Tools"   # type phrases, see what would happen
python -m unittest discover -s tests    # tests (QT_QPA_PLATFORM=offscreen on a headless box)
```

`tests/test_audio.py` runs synthetic speech (espeak-ng) through the real
recognizer end to end; it skips itself when espeak-ng or the model is missing.

**Building installers:** `.github/workflows/voice.yml` (at the repository root) builds the Mac `.dmg`
files (Apple Silicon and Intel) and the Windows setup `.exe` on GitHub's Mac
and Windows machines, runs the tests and a smoke test of each built app, and
publishes a release for tags like `voice-v0.2.0`. If these repository secrets are
set it also signs and notarizes the Mac build: `APPLE_CERT_P12` (base64
Developer ID Application certificate), `APPLE_CERT_PASSWORD`,
`APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`.
Locally: `pyinstaller limitless_voice.spec` (needs the model in `models/`).

**How it fits together:**

| File | Job |
|---|---|
| `app.py` | The window, menu bar icon, settings, permission checks |
| `onboarding.py` | The first-launch setup guide |
| `hud.py` | The floating card showing what was heard, and the state icons |
| `look.py` | Text size, high contrast and reduced motion for every window, from Voice's settings and the suite's |
| `audio.py` | Microphone (any device, any rate, survives unplugging) and recognition. Each utterance goes to two recognizers: one limited to command phrases (accurate on poor mics) and one open (for dictation and free text) |
| `engine.py` | Sleep/wake, dictation, confirm, repeat, picks the command for the app in front |
| `grammar.py` | Loads command files, matches phrases, builds the recognizer's phrase list |
| `platforms/` | Pressing keys, typing, finding and focusing apps, per OS |
| `numbers.py`, `keys.py` | Spoken numbers and key names |
| `voice_out.py` | Spoken feedback |
| `model.py` | Finds or downloads the speech model |

## What's next

1. **Run it on real Macs and PCs** with Logic Pro and Pro Tools and correct
   any shortcuts that differ.
2. **Sign the downloads** (Apple Developer ID, Windows code signing) so they
   install without warnings.
3. **Talk to tracks by name** ("solo the bass", "arm vocals") through the
   accessibility interfaces Logic and Pro Tools expose to screen readers.
4. **Mixer values by voice** ("track three volume minus six") through a
   virtual Mackie Control / HUI surface, which both DAWs support.
5. **More apps and languages:** command files for Studio One, REAPER,
   GarageBand and FL Studio; Vosk has models for 20+ languages. Ableton Live's
   single-letter keys (S solo, C arm, O metronome, A automation) do nothing
   while Live's Computer MIDI Keyboard is on: check them on a real Live 12.

## Works with the rest of Limitless Sound

When the Limitless Sound hub is running, Limitless Voice joins the suite by itself:

- **Say any app's actions.** "Screen colors on", "one hand mode", "next layer", "zoom keys
  off"... Your own commands always come first.
- **Take mode.** When a recording starts from any app (a controller button, GazeStage, your
  voice), Voice goes into take mode: only "stop" works, so lyrics and talk-back can't trigger
  commands. "Stop" ends the take and brings every command back. "All commands" ends take mode
  without stopping.
- **Voice works for the others.** Apps that can't press keys (GazeStage) can ask Voice to
  record, undo, save, mute and more, and anything can run a spoken command (`voice.do`).
- **One voice.** With that setting on, Voice's spoken replies go through the suite's one
  voice, and Voice stops listening while any app is being spoken for.
- **Set them once.** The suite's text size, high contrast and reduced motion settings change
  every Voice window, the setup guide and the floating card straight away. Where Voice has a
  setting of its own too, the more accessible one wins: the larger text, and high contrast if
  either is on. Reduced motion makes the floating card disappear at once instead of fading,
  and menus and lists open without animating. Voice tells the suite what it's using
  (`voice.prefs.applied`).

Without the hub nothing changes. The link is `limitless_voice/suite.py`, using a copy of
`shared/clients/python/limitless_link.py`.
