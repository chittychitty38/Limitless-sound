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
| `test_command_words.py` | Voice and Zoom hearing real people say their own command words ("record", "cut", "paste", "fit" ...), which Speech Commands doesn't have. See [Command words](#command-words) below. |
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

Every other voice test hears a synthetic voice (espeak-ng, or the Mac's `say`). These hear
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
- **Are the command words heard?** Real people saying "record", "cut", "paste", "fit" and the
  rest, which Speech Commands doesn't have. See [Command words](#command-words) below.

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

| Zoom | |
|---|---|
| Stray words: zoomed | 2.3% |
| Talk: zoomed per hour | 17.0, a third of them "again" |

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
- **Zoom's "again"** fires from ordinary talk about 6 times an hour.

The test also tries possible fixes on what it heard, without changing the app. The first, a
one-word destructive command needing the open recognizer to hear the same word, cost no word
above anything and is in Voice 0.3.5. The next, every one-word command needing that, would
bring stray words down from 17.9% to 1.3%, but "forward" would drop from 85% to 52% (the open
recognizer hears "for") and "stop" from 96% to 92%, so it isn't done. Speech Commands has no
"cut", "paste", "delete", "record" or "solo"; [Command words](#command-words) below measures
both rules on people really saying those.

### Command words

Speech Commands has "stop" and "forward", but none of the words Voice is mostly used for.
`test_command_words.py` hears those from the [Multilingual Spoken Words
Corpus](https://mlcommons.org/datasets/multilingual-spoken-words/) (MSWC): one-second clips of
single words, cut out of sentences people read aloud for Common Voice. So each word was said
inside a sentence, which is harder than a command said on its own: "stop" is right 77% to 79%
of the time here and 96% in Speech Commands ("forward" 92% here, 85% there). Up to 100 clips a
word, each from a different person; MSWC has only 11 people saying "quieter", 24 "taller" and
43 "mixer", and nobody saying "redo" or "metronome". `stress/tools/get_command_words.py` fetches
them: about 160 MB read out of MSWC's 35 GB English archive, every clip checked against its
Ogg CRCs.

What CI measured, Voice 0.3.6 with Logic Pro in front. Per word from one run; over three runs,
73.4% to 73.5% right, and no word moved by more than 3 clips in 100:

| Word | Right | Acts after the word | If every one-word command needed both recognizers | If none did |
|---|---|---|---|---|
| record | 86% | 0.53 s | 58% | 86% |
| play | 80% | 0.58 s | 59% | 79% |
| stop | 79% | 0.60 s | 68% | 78% |
| forward | 92% | 1.20 s | 61% | 92% |
| cut | **40%** | 1.03 s | 40% | 78% |
| copy | 84% | 1.21 s | 65% | 84% |
| paste | **44%** | 1.22 s | 44% | 84% |
| delete | **40%** | 1.21 s | 40% | 92% |
| undo | 85% | 1.22 s | 6% | 85% |
| save | 74% | 1.18 s | 50% | 74% |
| solo | 74% | 1.19 s | 36% | 74% |
| mute | 72% | 1.08 s | 37% | 72% |
| cycle | 89% | 0.95 s | 62% | 89% |
| mixer | 93% | 1.21 s | 28% | 93% |
| louder | 83% | 0.94 s | 53% | 83% |
| quieter | 100% | 1.16 s | 36% | 100% |
| fit | 74% | 1.06 s | 23% | 74% |
| **All 17** | **73.5%** | median 1.11 s | **47.0% to 47.4%** | **82.0% to 82.1%**, but 2 or 3 destructive keys for words not said |

"Acts after the word" is the median time from the end of the spoken word until Voice reports it.

Zoom 0.1.4 (three runs): 91.4% to 92.0% of its commands right: "fit" 87%, "taller" 24 of 25,
"shorter" 97%, "again" 89% to 91%. "zoom" alone, which isn't a command, never zoomed in 100 tries.

What it shows:

- **Cut, Paste and Delete are the weak spot, because of the 0.3.5 check.** The open recognizer
  hears people's "cut" as "god", "come" or "cup", "delete" as "the lead" or "elite", and "paste"
  as "based" or "pace", so the one-word destructive command doesn't fire. Without the check they'd
  be right 78%, 92% and 84% of the time, but a word that wasn't said would press a destructive key
  (2 or 3 times in these 1,505 clips; in Speech Commands, "cat" pressed Cut 64 times in 100).
- **Needing both recognizers for every one-word command would cost far more than it saves.**
  Commands would drop from 73.5% to about 47% right ("undo" 85% to 6%, "fit" 74% to 23%,
  "mixer" 93% to 28%), to bring Speech Commands' stray words down from 17.9% to 1.3%.
- **People's clipped "stop" comes back as "top"** 8 times in 100, which is Logic Pro's "go to
  start": the commonest wrong command, 10 of 21 to 24. None was destructive.
- **Record, Play and Stop act about half a second sooner** than the rest, as Voice 0.3.6 means
  them to: a median 0.53 to 0.60 s after the word, the rest 0.94 to 1.22 s.
- "taller", "shorter" and "zoom", which aren't Voice commands, fired one 1 or 2 times in 225.

Run it yourself (the downloads are 2.6 GB and 1 GB, once; the tests take about 17 minutes on 4
cores):

```sh
pip install vosk==0.3.44 soundfile pytest psutil numpy pyyaml platformdirs
python stress/tools/get_real_speech.py /tmp/real-speech
python stress/tools/get_command_words.py /tmp/command-words
VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15 SPEECH_COMMANDS_DIR=/tmp/real-speech/speech_commands \
  LIBRISPEECH_DIR=/tmp/real-speech/librispeech COMMAND_WORDS_DIR=/tmp/command-words \
  python -m pytest stress/test_voice_real_speech.py stress/test_zoom_real_speech.py stress/test_command_words.py -v -s
```

`REAL_SPEECH_PER_WORD` changes the 100 clips a word. Each time the recognizer is built it warns
about every command word the small model doesn't know; CI shows each warning once. The
sounds-alike spellings in `grammar.py` cover most of them, but not the app names "ableton",
"bitwig", "cubase" and "protools", so "open cubase" can't be heard as a command.

The recordings are not in this repository, and must not be committed. They are all under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Speech Commands: Pete Warden, "Speech Commands: A Dataset for Limited-Vocabulary Speech
  Recognition", 2018. Google.
- LibriSpeech: Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, "LibriSpeech:
  an ASR corpus based on public domain audio books", ICASSP 2015. From LibriVox recordings.
- Multilingual Spoken Words Corpus: MLCommons,
  [mlcommons.org/datasets/multilingual-spoken-words](https://mlcommons.org/datasets/multilingual-spoken-words/);
  Mazumder et al., 2021, NeurIPS Datasets and Benchmarks. Made from Mozilla Common Voice (CC0).

None of this replaces a person with a real mic, webcam, controller and DAW. That checklist is in
[HANDOFF.md](../HANDOFF.md).
