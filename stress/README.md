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
| `test_zoom_noise.py` | Limitless Zoom's commands said with a band playing under them, at three loudness levels: still heard? Does the band zoom by itself? |
| `test_control_stress.py` | Limitless Control: switch contact bounce, a trigger held at the threshold with a tremor, unplugging mid-press, every input mashed at once, a soak. |
| `test_zoom_stress.py` | Limitless Zoom: held switch and zoom keys, a lost key-up, a key storm, every action in every app. |
| `gazestage_stress.mjs` | GazeStage in Electron with a fake camera: lost focus with a switch held, a switch flood, a dwell flood, five relaunches, a 2+ minute tracking soak with memory sampling. |
| `color/` | Limitless Color's engine: every slider at every extreme, hostile profile files, 5,000 turns with the offline helper, the speed of rebuilding the screen filter. |

An app whose folder isn't in the checkout is skipped. `.github/workflows/stress.yml` runs it all on
Apple Silicon and Intel Macs, Windows and Linux (the real-people tests on Linux only): short soaks
on pull requests, 10-minute soaks nightly and on demand.

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

What CI measured (ubuntu-latest, October 2026; Voice 0.3.5 unless it says otherwise). Results
move a little from one runner's CPU to another's: over four runs, 91.2% to 91.6% of words right.
The tests' floors sit a little below what any run measured.

| Voice, with Logic Pro in front | |
|---|---|
| Words Voice listens for, said by real people | **91.4% right** (1645 of 1800) |
| Commands on their own: stop, no, forward | 96%, 96%, 85% |
| Numbers | three 96%, two 94%, one 93%, six 92%, seven 91%, zero 91%, four 90%, five 89%, nine 89%, eight 83% |
| Other words it listens for | yes 96%, right 95%, down 93%, left 93%, up 83% |
| Talk: commands fired per hour | **0** (Logic Pro), **3.8** (Pro Tools); **0 destructive**. Voice 0.3.4: 4.7 and 7.6 |
| Stray words that aren't commands: fired something | **17.9%** of the time; **never a destructive key**. Voice 0.3.4: 21.6%, a destructive key on 3.8% |

| How soon Voice acts after a word ends (median; 9 in 10 within) | |
|---|---|
| "stop", which goes the moment it's heard (Voice 0.3.6) | **0.67 s**; 0.77 s. Voice 0.3.5: 1.19 s; 1.36 s |
| Words that wait for the end of the utterance | 1.13 s; 1.28 s |

| Zoom 0.1.4 | |
|---|---|
| Stray words: zoomed | 2.2% |
| Talk: zoomed per hour | **3.8**, all "shorter" or "fit" heard on its own. Zoom 0.1.2: 17.0, nearly all a command word inside a sentence |

What goes wrong, from the printed tables:

- **A stray word fires the nearest command.** The command recognizer can only answer with
  command words, so a short word that isn't one comes back as the closest that is. Out of 100
  people each: "happy" fires Copy 80 times; "wow" 60 times, nearly all volume up; "follow" 55
  times, nearly all Solo; "bird" 27 times, mostly Record. The open recognizer hears the real word
  nearly every time ("copy / happy"). Voice 0.3.4 also pressed Cut for "cat" 64 times in 100;
  since 0.3.5 a one-word Cut, Paste or Delete needs the open recognizer to hear it too.
- **Talk in full sentences rarely fires anything**, and nothing destructive. Voice 0.3.4 acted
  on the command recognizer's guess at a sentence it mostly couldn't place ("[unk] enter [unk]
  [unk]" pressed Return, "stop [unk] [unk] [unk]" pressed Play) and on a half-heard "open the
  [unk] [unk] that" (an app called "the that"). Since 0.3.5 those go by the open transcript. What
  still fires in Pro Tools is short: "heal separation [unk] a" for "illustration long pepper".
- **People's "eight" comes back as "a"** 6 times in 100, and "forward" as "four" 9 times.
- **Zoom acted on command words inside sentences**: "…had to see again", "for ink" heard as
  "zoom in". Since 0.1.4 a command with another word running straight on from it (less than
  0.1 s between, by Vosk's word times) doesn't count, while "please", "uh" and "okay" around it
  are fine. That took talk from 17 zooms an hour to 3.8, and cost nothing with a band playing
  (`test_zoom_noise.py`).
- **Voice waited up to a second to act**, for its open recognizer to end the utterance. Since
  0.3.6 play, stop and record go as soon as the command recognizer has heard just that.

The test also tries possible fixes on what it heard, without changing the app. The first, a
one-word destructive command needing the open recognizer to hear the same word, cost no word
above anything and is in Voice 0.3.5. The next, every one-word command needing that, would
bring stray words down from 17.9% to 1.3%, but "forward" would drop from 85% to 52% (the open
recognizer hears "for") and "stop" from 96% to 92%, so it isn't done. Speech Commands has no
"cut", "paste", "delete", "record" or "solo", so what such a rule costs people who really say
them isn't measured here; recordings of real people saying those words would settle it.

Run it yourself (the downloads are 2.6 GB, once; the tests take about 12 minutes on 4 cores):

```sh
pip install vosk==0.3.44 soundfile pytest psutil numpy pyyaml platformdirs
python stress/tools/get_real_speech.py /tmp/real-speech
VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15 SPEECH_COMMANDS_DIR=/tmp/real-speech/speech_commands \
  LIBRISPEECH_DIR=/tmp/real-speech/librispeech \
  python -m pytest stress/test_voice_real_speech.py stress/test_zoom_real_speech.py -v -s
```

`REAL_SPEECH_PER_WORD` changes the 100 clips a word. Each time the recognizer is built it warns
about every command word the small model doesn't know; CI shows each warning once. The
sounds-alike spellings in `grammar.py` cover most of them, but not the app names "ableton",
"bitwig", "cubase" and "protools", so "open cubase" can't be heard as a command.

The recordings are not in this repository, and must not be committed. They are both under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Speech Commands: Pete Warden, "Speech Commands: A Dataset for Limited-Vocabulary Speech
  Recognition", 2018. Google.
- LibriSpeech: Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, "LibriSpeech:
  an ASR corpus based on public domain audio books", ICASSP 2015. From LibriVox recordings.

None of this replaces a person with a real mic, webcam, controller and DAW. That checklist is in
[HANDOFF.md](../HANDOFF.md).
