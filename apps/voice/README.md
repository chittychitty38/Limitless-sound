# Limitless Voice

Control Logic Pro, Pro Tools, Ableton Live, GarageBand, REAPER, FL Studio and the rest of your
computer with your voice.
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
| **Language** | English (US) built in. Spanish, for Latin America and Spain, is a 39 MB download from Settings, once. A larger English model and an Indian English model can be downloaded from Settings too. |
| **Apps** | Ready-made commands for Logic Pro and GarageBand 10 (Mac), Pro Tools, Ableton Live 12, REAPER 7 and FL Studio (Mac and Windows). Everything else works through the everyday commands (copy, undo, open apps, arrows...), "press ..." for any shortcut, and your own command files. |

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

## Languages

Voice listens and answers in English or Spanish. Choose in Settings > Language:

- **Same as Limitless Sound** (the default): the language chosen for the whole suite on the
  Limitless Sound page. Without the hub, English, as always.
- **English** or **Español**: that one, whatever the suite's is.

Spanish is downloaded once (39 MB) the first time it's chosen, then works without internet.
Until it's here (offline, say), Voice keeps listening in English, says so in its window, and
offers the download again.

Its commands are the English ones, said the way Spanish-speaking musicians say them, with
Latin America's and Spain's words both: "ir al compás treinta y dos", "graba", "dale play",
"parar", "solo", "silenciar la pista" or "mute", "loop", "deshacer", "añadir pista" or "agregar
pista", "mostrar el mezclador", "pulsa comando mayúsculas ene", "desplazar a la derecha cuatro
veces". Say "qué puedo decir" for the list, "a dormir" and "despierta", "sí" and "cancelar",
"empezar dictado" and "terminar dictado". Cut, Paste, Delete and Duplicate are said whole when
said alone ("cortar", "pegar", "eliminar" or "borrar", "duplicar"), never "corta": a word that
sounds like one of them must never throw work away.

Replies are read by a Spanish voice when the computer has one. When it hasn't, Voice says where
to add one: on a Mac, System Settings > Accessibility > Spoken Content > System voice > Manage
Voices; on Windows, Settings > Time & language > Speech > Add voices. With the suite's one voice
on, the hub reads them in Spanish. Other apps' actions ("screen colors on") are only heard in
English for now, as the apps name them in English. Voice's windows (the main window, Settings,
the setup guide, the menu bar menu and the floating display) change to the language chosen at
once, even before its speech model is here; the commands they suggest saying are the ones Voice
hears, so they stay English until then.

How well it hears real people, measured in CI (Voice 0.4.0; `stress/README.md` has how):

| | English | Spanish |
|---|---|---|
| Command words said by real people, right at once (one word each, cut out of sentences) | 73% | 83% |
| Right at once or after a "yes" | 82% | 84% |
| Cut, Paste or Delete pressed for a word that wasn't said | never | never |
| An hour of people reading aloud: commands fired in Logic Pro / Pro Tools | 0 / 3.8 | 1 / 0 |
| How soon a command acts after the word ends | 1.1 s | 1.4 s |
| Play, stop and record | 0.6 s | 0.6 s |

The words aren't the same in the two languages, so this says each one does its job rather
than that one is better. Spanish's speech model is Alpha Cephei's small Spanish model,
under the Apache 2.0 licence, like the English one.

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
[DAW-SHORTCUTS.md](DAW-SHORTCUTS.md) gives the official source for each key in
the Ableton Live, GarageBand, REAPER and FL Studio packs, and what's still
unconfirmed.

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
| `words.py` | The windows' words in Voice's language, from the language's `texts`, changing in place when it changes |
| `audio.py` | Microphone (any device, any rate, survives unplugging) and recognition. Each utterance goes to two recognizers: one limited to command phrases (accurate on poor mics) and one open (for dictation and free text) |
| `engine.py` | Sleep/wake, dictation, confirm, repeat, picks the command for the app in front |
| `grammar.py` | Loads command files, matches phrases, builds the recognizer's phrase list |
| `platforms/` | Pressing keys, typing, finding and focusing apps, per OS |
| `language.py`, `languages/` | Each language's words: its phrases for every built-in command, its own words (wake, sleep, yes, cancel...), numbers, key names and replies. The packs stay English |
| `numbers.py`, `keys.py` | Spoken numbers and key names, from the language's tables |
| `voice_out.py` | Spoken feedback |
| `model.py` | Finds or downloads the speech model |

**Adding a language** takes a speech model, one file, and measurements:
1. A Vosk model under a permissive licence (Apache 2.0 or the like, not GPL), listed with its
   size in the new `languages/<code>.yaml`.
2. That file, copied from `languages/es.yaml`: the language's phrases for every command in the
   built-in packs (by each command's first English phrase), its own words, numbers table, key
   names, and every reply. `tests/test_language.py` fails until every command has phrases and
   every reply a translation.
3. `stress/test_voice_language.py` against the model: every word Voice listens for must be one
   it knows (it prints the nearest words it does know). Then real people: the Multilingual
   Spoken Words Corpus's clips of its command words (`stress/tools/get_command_words.py --lang`)
   and an hour of FLEURS read aloud (`stress/tools/get_fleurs.py --lang`), with floors in
   `stress/test_command_words.py` and `stress/test_voice_real_speech.py`, and a job in
   `.github/workflows/stress.yml`.

## What's next

1. **Run it on real Macs and PCs** with Logic Pro and Pro Tools and correct
   any shortcuts that differ.
2. **Sign the downloads** (Apple Developer ID, Windows code signing) so they
   install without warnings.
3. **Talk to tracks by name** ("solo the bass", "arm vocals") through the
   accessibility interfaces Logic and Pro Tools expose to screen readers.
4. **Mixer values by voice** ("track three volume minus six") through a
   virtual Mackie Control / HUI surface, which both DAWs support.
5. **More apps and languages:** a command file for Studio One; Vosk has
   models for 20+ languages (see Adding a language above). Ableton Live's
   single-letter keys (S solo, C arm, O metronome, A automation) do nothing
   while Live's Computer MIDI Keyboard is on: check them on a real Live 12.
6. **Check GarageBand, REAPER and FL Studio on real computers**, and add the
   keys their official guides couldn't confirm from here (GarageBand's cycle,
   metronome and zoom; REAPER's zoom). The list is in
   [DAW-SHORTCUTS.md](DAW-SHORTCUTS.md).

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
