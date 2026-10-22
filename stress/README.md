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
| `test_voice_real_speech.py` | Limitless Voice hearing real people, not a synthetic voice: thousands of people saying single words, and an hour of people reading aloud. See [Real people](#real-people) below. |
| `test_zoom_real_speech.py` | Limitless Zoom hearing the same recordings: do stray words or ordinary talk zoom the screen? |
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

## Real people

Every other voice test hears a synthetic voice (espeak-ng, or the Mac's `say`). These two hear
recordings of real people, fed to the apps the way a microphone's audio is: in 100 ms blocks
through Voice's two recognizers and into its command engine, and through Zoom's own gate and
recognizer.

- **Is a word heard?** [Google Speech Commands](https://arxiv.org/abs/1804.03209) v0.02, its
  official test split: one-second clips of single words, each said by a different person into
  their own phone or laptop. 100 clips of each of its 35 words, from about 200 people. A word
  counts as right when Voice does exactly what it does when it hears the word perfectly. For
  numbers, "to" counts as "two" and "for" as "four", because the engine reads them that way
  after "bar", "track" or "tempo". Its words that aren't Voice commands on their own ("go",
  "off", "cat", "happy") should do nothing.
- **Does ordinary talk fire commands?** An hour of [LibriSpeech](https://www.openslr.org/12)
  dev-clean: 40 people (20 women, 20 men) reading books aloud, 95 seconds each. None of it is
  meant as a command, so everything it fires is a false trigger.

What CI measured (ubuntu-latest, October 2026). The tests' floors sit a little below these.

| Voice, with Logic Pro in front | |
|---|---|
| Words Voice listens for, said by real people | **91.2% right** (1642 of 1800) |
| Commands on their own: stop, no, forward | 96%, 95%, 86% |
| Numbers | three 96%, two 94%, one 93%, seven 91%, six 91%, zero 91%, four 90%, nine 89%, five 88%, eight 82% |
| Other words it listens for | yes 96%, right 95%, down 93%, left 92%, up 84% |
| Talk: commands fired per hour | **1.9** (Logic Pro), **4.7** (Pro Tools); **0 destructive** |
| Stray words that aren't commands: fired something | **21.6%** of the time; a destructive key on 3.8% |

| Zoom | |
|---|---|
| Stray words: zoomed | 2.3% |
| Talk: zoomed per hour | 17.9, a third of them "again" |

What goes wrong, from the printed tables:

- **A stray word fires the nearest command.** The command recognizer can only answer with
  command words, so a short word that isn't one comes back as the closest that is. Out of 100
  people each: "cat" fired a command 68 times, 64 of them Cut (Cmd+X); "happy" fired Copy 80
  times; "wow" 59 times, nearly all volume up; "follow" 55 times, Solo; "bird" 27 times, mostly
  Record. The open recognizer heard the real word nearly every time ("cut / cat"). Talk
  in full sentences is fine: an hour of it fired a handful of commands and nothing destructive.
- **People's "eight" comes back as "a"** 6 times in 100, and "forward" as "four" 9 times.
- **Zoom's "again"** fires from ordinary talk about 6 times an hour.

Run it yourself (the downloads are 2.6 GB once; the test takes about 15 minutes on 4 cores):

```sh
pip install vosk==0.3.44 soundfile pytest psutil numpy pyyaml platformdirs
python stress/tools/get_real_speech.py /tmp/real-speech
VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15 SPEECH_COMMANDS_DIR=/tmp/real-speech/speech_commands \
  LIBRISPEECH_DIR=/tmp/real-speech/librispeech \
  python -m pytest stress/test_voice_real_speech.py stress/test_zoom_real_speech.py -v -s
```

`REAL_SPEECH_PER_WORD` changes the 100 clips a word.

The recordings are not in this repository, and must not be committed. They are both under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Speech Commands: Pete Warden, "Speech Commands: A Dataset for Limited-Vocabulary Speech
  Recognition", 2018. Google.
- LibriSpeech: Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, "LibriSpeech:
  an ASR corpus based on public domain audio books", ICASSP 2015. From LibriVox recordings.

None of this replaces a person with a real mic, webcam, controller and DAW. That checklist is in
[HANDOFF.md](../HANDOFF.md).
