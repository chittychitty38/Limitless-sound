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
