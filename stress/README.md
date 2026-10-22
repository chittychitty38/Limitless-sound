# Stress tests

The apps pushed the way a hard day in the studio pushes them. Each test is written from what
would hurt a musician: a command firing twice from one shaky press, a held note that never
stops, a destructive command firing from noise, an app that freezes the rest of the suite,
memory that keeps climbing over a long session.

| File | What it does |
|---|---|
| `test_hub_stress.py` | The hub on real sockets: six apps flooding it while a musician presses a switch, a frozen app, 300 crash-and-reopen cycles, garbage on the wire, link loops, two copies of one app, a soak. |
| `test_onehand_stress.py` | One-Hand's key engine: tremor holding and bouncing on command keys, a million random key events, per-key speed for the macOS hook, fast Shift typing, a soak. |
| `test_voice_stress.py` | Limitless Voice: one misheard utterance must not wreck a session, asleep means asleep, chatter rarely fires. With the real speech model: white, pink, hum and band noise for two minutes each, people talking, and spoken commands under music at three loudness levels. |
| `test_control_stress.py` | Limitless Control: switch contact bounce, a trigger held at the threshold with a tremor, unplugging mid-press, every input mashed at once, a soak. |
| `test_zoom_stress.py` | Limitless Zoom: held switch and zoom keys, a lost key-up, a key storm, every action in every app. |
| `gazestage_stress.mjs` | GazeStage in Electron with a fake camera: lost focus with a switch held, a switch flood, a dwell flood, five relaunches, a 2+ minute tracking soak with memory sampling. |
| `color/` | Limitless Color's engine: every slider at every extreme, hostile profile files, 5,000 turns with the offline helper, the speed of rebuilding the screen filter. |

An app whose folder isn't in the checkout is skipped. `.github/workflows/stress.yml` runs it all on
Apple Silicon and Intel Macs, Windows and Linux: short soaks on pull requests, 10-minute soaks
nightly and on demand.

## Run it yourself

```sh
pip install pytest psutil numpy pyyaml platformdirs pygame-ce==2.5.8
python -m pytest stress -v -s                     # STRESS_SECONDS=600 for long soaks

# Voice against real noise and speech (needs the model and spoken clips)
pip install vosk==0.3.44
python stress/tools/make_speech.py /tmp/speech    # uses `say` on a Mac
VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15 TTS_WAV_DIR=/tmp/speech python -m pytest stress/test_voice_stress.py -v -s

# GazeStage
cd apps/gazestage && npm ci && node ../../stress/gazestage_stress.mjs

# Color
cargo test --release --manifest-path stress/color/Cargo.toml -- --nocapture
```

`STRESS_REPO_ROOT=/some/other/checkout` points the Python tests at another checkout, for
example an app's branch before it merges.

None of this replaces a person with a real mic, webcam, controller and DAW. That checklist is in
[HANDOFF.md](../HANDOFF.md).
