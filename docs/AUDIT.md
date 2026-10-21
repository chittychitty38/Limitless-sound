# Where each app really stands

Written 21 October 2026, after stress testing every app. Plain answer first: **every app
compiles, installs on GitHub's Mac and Windows build machines, and passes its own tests and the
stress suite. None of them has yet been used on a real Mac by a real musician with a real
microphone, webcam, controller or DAW.** Those are the things a build machine can't do, and
they are exactly what [HANDOFF.md](../HANDOFF.md) walks through.

What "tested" means below:

- **Unit tested**: the app's logic is checked by its own tests on every change.
- **Stress tested**: pushed hard by [`stress/`](../stress) (floods, tremor, held keys, noise,
  hung and crashing apps, long soaks). Results are from 21 October 2026.
- **Built and launched in CI**: GitHub's Mac and Windows machines build the installer and
  start the app. They have no screen, mic, camera, controller, DAW or privacy permissions, so a
  launch check proves the app starts, not that it works.
- **Never tried for real**: needs a person at a Mac. See HANDOFF.md.

## Bugs the stress tests found

| App | What happened | Status |
|---|---|---|
| One-Hand | Holding a command key fired it on every key auto-repeat: 5,000 shaky presses fired 24,850 commands (Record toggling on and off). Holding the F18 switch flipped one-hand mode over and over. | Fixed in this PR: 5,000 presses give 5,000 commands. |
| One-Hand (Mac) | A missed modifier release (or letting go of one of two held Command keys) left the modifier "held" forever, so one-hand mode silently stopped working. | Fixed in this PR. |
| Hub | While a closed app's command line ran (up to 10 s), the whole suite froze. | Fixed on PR #7 (1.4 s stall → 52 ms). |
| Hub | A message could carry a negative step count and run a link loop past the 4-step safety limit (17 steps). | Fixed on PR #7. |
| Hub | Two copies of the same app knocked each other off the hub forever (30 reconnects in 3 s). | Fixed on PR #7. |
| GazeStage | A note held with a switch kept sounding forever when the window lost focus, and the switch stopped working. | Fixed on PR #11. |
| Voice | "Delete fifty times" pressed Delete 50 times from one utterance; same for cut and paste. One misheard phrase could wipe a session. | Sent to the Voice thread. |
| Control | A trigger held near its threshold with a tremor fired 9 commands in 3 seconds. | Sent to the Control thread. |

## App by app

### Limitless Sound hub (`shared/hub`, PR #7)
- Unit tested (54 tests on PR #7), stress tested on real sockets: six apps flooding ~2,000
  actions a second while a musician's press still lands in ~40 ms (p50); a frozen app doesn't
  hold up the others; 300 crash-and-reopen cycles leak nothing; garbage on the wire can't take
  it down; memory flat over a soak.
- Built and launched in CI. Never run on a real Mac with several real apps connected at once.

### Limitless One-Hand (`apps/one-hand`, on main; PR #10 adds Mac polish)
- Unit tested, stress tested (tremor, a million random key events, 12 µs per key, fast
  Shift typing never toggles it by accident).
- **The Mac keyboard hook has never run.** CI's Mac self-test reports success even when macOS
  refuses the hook (build machines have no Accessibility permission), so it proves the app loads,
  not that it catches keys. The Windows hook does run in CI.
- DAW shortcuts in `layouts.json` are from the manuals, not checked in Logic or Pro Tools.

### Limitless Voice (`apps/voice`, PR #1)
- Unit tested, including synthetic speech (espeak-ng) through the real recognizer.
- Stress tested at the engine level. The real-recognizer stress tests (two minutes each of
  white noise, pink noise, mains hum and a band playing; studio chatter; spoken commands under
  music at three loudness levels) run in the Stress tests workflow on Mac and Linux. They
  could not run in the sandbox these tests were written in, so their first results come from CI.
- Never heard a real voice through a real Mac microphone. Accuracy on a cheap mic, with a
  speech difference, or with a band playing is unknown.

### Limitless Zoom (`apps/zoom`, PR #6)
- Unit tested (31), stress tested (held keys, lost key-ups, key storms, every action in every
  app): no failures.
- The Mac key capture and the zoom shortcuts for Logic, Pro Tools, Ableton and GarageBand are
  untried on a real Mac.

### Limitless Color (`apps/color`, PR #2)
- The color engine is unit tested and stress tested: every slider at every extreme gives a sane
  screen, hostile profile files can't crash it, 5,000 turns with the offline helper stay in
  range, a full screen-filter rebuild takes ~17 ms.
- **The Mac screen filter (ScreenCaptureKit + Metal overlay) has never drawn on a real
  screen.** Screen Recording permission, lag, multiple displays, Retina scaling and what happens
  if the app crashes with colors on are all untried.

### Limitless Control (`apps/control`, PR #3)
- Unit tested, stress tested: switch contact bounce never double-fires, unplugging mid-press
  stops repeats, 100,000 random presses leave nothing stuck.
- **Never used with a real Xbox Adaptive Controller** (or any controller) on a Mac. Whether
  macOS delivers controller input while Logic or Pro Tools is in front is the big unknown.

### GazeStage (`apps/gazestage`, PR #11, version 0.3)
- Unit tested, end-to-end smoke tested with a fake camera, stress tested: switch and dwell
  floods leave nothing sounding, 5 of 5 relaunches start the camera, memory settles after about a
  minute and stays flat.
- **Never tracked a real face.** Pointer accuracy, comfort, lighting, glasses, and frame rate on
  a real Mac (CI machines have no graphics chip and manage 9 frames a second) are unknown.
- The Pro Tools HUI codes for rewind, fast forward and stop are unconfirmed.

## Everything, every app

- **Unsigned.** macOS asks for "Open Anyway" the first time. An Apple Developer ID removes that.
- **Permissions** (Accessibility, Input Monitoring, Microphone, Camera, Screen Recording) can
  only be granted and checked on a real Mac.
- **No musician has used any of it yet.** Default timings (dwell, cooldowns, tremor filters)
  are educated guesses until real players try them.
