**One download for the whole Limitless Sound suite, on Mac or Windows.** On a Mac, pick the file for your Mac:

- **Apple silicon (M1 and later):** `Limitless-Sound-Suite-mac-apple-silicon.pkg`
- **Intel Mac:** `Limitless-Sound-Suite-mac-intel.pkg`

(The `.dmg` files hold the same installer, for older links.)

Not sure which you have? Open the Apple menu and choose About This Mac. If "Chip" says Apple, use Apple silicon. If "Processor" says Intel, use Intel.

### Install
1. Double-click the installer you downloaded.
2. The first time, macOS says it can't check the developer. Click **Done**, open **System Settings › Privacy & Security**, scroll down, click **Open Anyway**, and confirm. You only need to do this once, for the whole suite.
3. The Mac installer opens. Click **Continue**, then **Install**, and type your Mac's password. If you picked the download for the other kind of Mac, it tells you which one to get.
4. Every app is in Applications. Limitless Sound starts, says "Limitless Sound is installed", and its page opens in your browser with two quick questions: how you like to play, and how things should look. Then it opens the apps that fit you.

### New in 0.2.5
- **The first step to Limitless Sound in Spanish.** Choose English or Español once, in the first two questions or in Settings, and every app that has Spanish follows it. A computer set to Spanish starts in Spanish.
  - The installers are in Spanish on a Spanish Mac or PC.
  - So is Limitless Sound's own page: the two questions, every tab and every setting.
  - When an app speaks Spanish, its replies are read by a Spanish voice. If the computer has none, the page says where to add one.
  - Limitless Voice in Spanish, and the other apps' windows, are coming next.
- **Limitless Voice works in Ableton Live 12**, on Mac and Windows: play, record, metronome, loop, new audio and MIDI tracks, solo, mute, arm, split, consolidate, quantize, delete, mixer, browser, clip view, automation, zoom and export. Voice 0.3.9.
- **Every app presses the same key for the same thing.** We checked every app's DAW keys against the others and against Apple's, Avid's and Ableton's guides. Six were wrong:
  - In Logic Pro, "mute" and "solo" in Voice and One-Hand muted and soloed regions instead of the track. They now press M and S.
  - In Pro Tools on a Mac, "record" in Voice and One-Hand pressed Command-Space, which opens Spotlight. One-Hand told you to switch Spotlight's shortcut off. Both now press F12, with nothing to set up.
  - In Pro Tools, Voice's "next track" and "previous track" only worked with Commands Keyboard Focus on. They now press Control-; and Control-P.
  - In Pro Tools, Control's "go to end" pressed Command-Return. It now presses Option-Return.
  - In Ableton Live on Windows, Control's "redo" pressed Ctrl+Shift+Z. It now presses Ctrl+Y.
  - A test now checks every app against the others on every change, so they can't drift apart again. Control 0.2.6, One-Hand 0.2.4.

### New in 0.2.4
- **Every app works with a screen reader and the keyboard alone, and every app's tests now check it.**
  - VoiceOver reads what Voice heard and what it did. It used to say only "Last thing heard".
  - Every button is named in words: Zoom's "−" and "+" are "Zoom out" and "Zoom in".
  - A status line is read again when it changes.
  - Tab reaches every control, in the order they're shown. One-Hand used to skip the hand that wasn't chosen.
  - Tab no longer wanders into controls you can't see: GazeStage's closed settings drawer used to hold 42 of them.
  - Escape cancels choosing a Zoom key.
  - Every screen made of web pages passes the WCAG 2.2 AA accessibility standard, in light and dark, high contrast and the largest text: Limitless Sound's page, Control's, GazeStage, Color and the Mac installer.
- **"Stop" stops twice as fast.** Limitless Voice 0.3.6 acts on play, stop and record the moment it has heard them, instead of waiting for you to finish speaking. On recordings of real people, "stop" now takes effect about two-thirds of a second after the word ends, down from more than a second. Every other command still waits, so a slow "nudge right … four times" still works.
- **Limitless Voice no longer acts on words that weren't commands.** We played it recordings of about 200 real people saying single words, and an hour of 40 people reading aloud. Voice now:
  - never pressed Cut, Paste or Delete for a word that wasn't one. Before, people's "cat" pressed Cut 64 times in 100. Voice listens twice, once for commands and once for any words, and when the second listener didn't hear "cut", "paste" or "delete" too, Voice 0.3.8 asks "Say yes to cut, or cancel" instead of doing it.
  - fired no command at all in that hour of talk with Logic Pro in front (4.7 before), and 3.8 with Pro Tools (7.6 before), none of them destructive.
  - still hears the words it listens for just as well: 91% of them, said by about 200 different people into their own phones and laptops.
  - opens only an app it heard the name of. On Windows, "open it" could start any app with "it" in its name.
- **Cut, paste and delete work when you say them.** Real people's "delete" is often heard as "the lead", "paste" as "based" and "cut" as "god". Voice 0.3.8 asks instead of refusing, so a yes gets them done: on the same recordings, "delete" now works 92 times in 100 at once or with a yes, "paste" 84 and "cut" 78, up from 37, 45 and 40. Saying anything other than yes or cancel after a question runs as a new command, so a question asked by mistake never swallows your next one.
- **"Stop" no longer sends you back to the start.** People's "stop" was heard as "top" 8 times in 100, and "top" alone meant "go to start" in Logic Pro and Pro Tools. It's gone: say "go to start" or "go to the top".
- **Limitless Voice rests in a quiet room.** Voice 0.3.7 doesn't work on silence. It used to spend about 6% of a processor core listening to an empty room, all the time it was on. The second before each sound is kept, so the start of a command is never cut off.
- **Limitless Zoom hardly ever zooms while you talk.** A command word said inside a sentence no longer counts, while "zoom in please" still does. In the same hour of people reading aloud, Zoom 0.1.4 zoomed 4 times, down from 17. With a band playing under the commands, it still heard 41 of 42 said by three of the Mac's voices, and all of them on Linux.
- **GazeStage's tone pad works while it's minimised.** In 0.2.3, when Voice, a controller or another app moved the tone pad while GazeStage was minimised, the Helix or plugin got nothing until GazeStage's window came back. GazeStage 0.4.2 sends the tone pad's MIDI on its own clock, so it goes out on time whatever is in front.
- **The tone pad's commands follow the Limitless Access Standard.** GazeStage 0.4.2 gives them names the standard allows, so it keeps its level, and Voice, a controller or a Stream Deck can use them the standard way ("tone A" still works). Found by installing 0.2.3 on fresh computers and checking every app.

### New in 0.2.3
- **GazeStage's tone pad.** A new Tone page (⌘3) shapes your sound the way the pads play it: with your eyes, your head, dwell or a switch. One point sends two MIDI controllers, left–right and down–up.
  - It drives a Line 6 Helix, HX or POD Go's expression pedals when one is plugged in by USB, or any plugin through MIDI learn.
  - Look and hold still to place the point, or let it follow you for live sweeps. Save four tones and come back to them.
  - Voice and the other apps can move it too ("tone A").
  - Without a Helix it's still audible: **Listen** holds a chord on the built-in sound and the pad shapes it.
- **Limitless Control rests while its settings page is open.** The page used to ask Control for news six times a second, about 3% of an older Mac's processor. Now Control tells the page the moment something changes (a press shows at once) and otherwise checks in every 2 seconds.
- **The website meets the WCAG 2.2 AA accessibility standard**, checked automatically on every change. The small text on its red buttons is now easier to read.

### New in 0.2.2
- **GazeStage sits quietly while it waits.** Sitting idle it now uses under 1% of the processor in our tests on Apple silicon and Intel Macs. It used to use about 6%, which runs a laptop's battery down through a session. Three things kept it busy:
  - Its built-in instrument kept the computer's audio running for a minute after any sound, a selection click included. Now the audio rests 10 seconds after the last sound has died away. It wakes again as soon as you look or point at something that will sound, so the first note after a rest still plays on time.
  - It redrew the status bar every second, even when nothing on it had changed.
  - It woke the window's drawing four times a second to check for changes.

### New in 0.2.1
Every change here was found by installing 0.2.0 from this page on fresh Apple silicon and Intel Macs and a fresh Windows PC, opening every app and pressing every button it offers to the rest of the suite.

- **Limitless Control starts in about a second on every Mac.** In 0.2.0 it could take 37 seconds while it looked up the computer's network name, which it never needed. (0.2.0's notes said this was fixed; it wasn't.) Limitless Sound skips the same lookup.
- **GazeStage answers every other app at once, even on a Mac whose sound output isn't working.** Its built-in instrument now plays on its own, so starting the computer's audio can never freeze the window: on such a Mac, Voice or a controller pressing Play used to get no answer for 20 seconds.
- **Limitless Zoom sits quietly while it waits.** It used to keep 5 to 7% of an older Mac's processor busy listening to a silent room; now it skips silence (always hearing the start of a command) and stops redrawing what hasn't changed: under 1% in our tests. Opening it twice never runs two copies.
- **Crash logs only hold real crashes.** On Windows they also listed problems Windows had already handled, which read like crashes.

### New in 0.2.0
- **A guided setup.** The first time Limitless Sound opens, it asks how you like to play (your voice, one hand, eyes or head, a switch or foot pedal, an adaptive controller, colour vision, bigger text and zoom) and how things should look and sound. One button opens the apps that fit and makes them open together every time.
- **One set of settings for every app.** Text size, high contrast and reduced motion, chosen once, are followed live by every app, and each app's card shows that it's using them.
- **Quiet when you're not playing.** One-Hand, Zoom, Color, Control and GazeStage barely touch the processor while waiting, so they're safe to leave running through a session.
- **Fixes:**
  - Zoom no longer crashes on its first zoom on Apple silicon.
  - A refusal from any app always says why. Saying "play" with no DAW in front, Voice says to bring Logic Pro or Pro Tools forward instead of "didn't catch".
- **Log files**, so a problem can be found after the fact and sent along when you ask for help. Limitless Sound and every app keep one; **Activity › Open the log folder** on the settings page shows them.

### What's inside
| App | What it does |
|---|---|
| Limitless Sound | Joins the apps into one suite, so any input can trigger any tool. Runs quietly in the background. |
| Limitless Voice | Voice commands for Logic Pro, Pro Tools and the whole computer, fully offline. |
| Limitless One-Hand | Turns the keys under one hand into DAW commands. |
| Limitless Zoom | Zooms the DAW or the screen by voice, one hand, dwell or a switch. |
| Limitless Color | Recolors the whole screen for colorblind musicians. |
| Limitless Control | Turns the Xbox Adaptive Controller, switches and gamepads into DAW commands. |
| GazeStage | Plays instruments and runs the transport with your eyes, head or a sound. |

### Windows
Download `Limitless-Sound-Suite-windows.exe` and run it. It installs every app and Limitless Sound for you, with no administrator needed, and Limitless Sound starts when you sign in. If SmartScreen appears, choose **More info › Run anyway**. Each app is listed in **Settings › Apps** under its own name, so any one can be removed by itself.

Each app also works on its own, and each has its own release page with Mac and Windows downloads.
