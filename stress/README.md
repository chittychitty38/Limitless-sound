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
| `test_zoom_real_speech.py` | Limitless Zoom hearing the same recordings: do stray words or ordinary talk zoom the screen? In Spanish too: see [Zoom in Spanish](#zoom-in-spanish) below. |
| `test_zoom_language.py` | Every word Zoom listens for in a language is one its speech model knows, and real people saying Zoom's Spanish command words. See [Zoom in Spanish](#zoom-in-spanish) below. |
| `test_command_words.py` | Voice and Zoom hearing real people say their own command words ("record", "cut", "paste", "fit" ...), which Speech Commands doesn't have. See [Command words](#command-words) below. |
| `test_voice_language.py` | Every word Voice listens for in a language is one its speech model knows. See [Spanish](#spanish) and [Portuguese](#portuguese) below. |
| `test_zoom_noise.py` | Limitless Zoom's commands said with a band playing under them, at three loudness levels: still heard? Does the band zoom by itself? In English, and every Spanish phrase. |
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
sounds-alike spellings in `apps/voice/limitless_voice/languages/en.yaml` cover most of them, but not the app names "ableton",
"bitwig", "cubase" and "protools", so "open cubase" can't be heard as a command.

### Spanish

Voice in Spanish (`VOICE_LANGUAGE=es`) gets the same two checks with Spanish recordings, in
its own CI job:

- **Command words:** MSWC's Spanish clips of Voice's Spanish command words, cut from sentences
  people read for Common Voice, with Logic Pro in front, judged as above; number words, which
  alone do nothing ("heard as itself"); and words that sound like a command and aren't
  ("pagar" and "pegar", "corto" and "cortar", "guardia" and "guardar"). Voice listens for other
  forms of its command words ("grabado", "unión"), so those count as words it listens for, not
  stray words. MSWC has no clip of a word shorter than three letters ("sí", "no") and few of
  some commands ("borrar" 7, "suprimir" 5).
- **Ordinary talk:** an hour of [FLEURS](https://arxiv.org/abs/2205.12446) Latin American
  Spanish (es_419): Wikipedia sentences read aloud by native speakers, the first hour of its
  dev split. FLEURS doesn't say who read what, so the hour is cut into 40 stretches, each heard
  as one person reading.
- **Vocabulary:** every word Voice listens for is one the Spanish model knows
  (`test_voice_language.py`, which also runs for English).

What CI measured, Voice 0.4.0 in Spanish with Logic Pro in front (two runs), next to English the
same day:

| | Spanish | English |
|---|---|---|
| Command words right at once | **83.5% to 83.6%** (1,657 clips, 40 words) | 73.6% to 73.7% (1,505 clips, 17 words) |
| At once or with a yes | **84.2%** | 82.3% |
| Destructive key from a word not said | 0 | 0 |
| Stray words that fired a command | 6.2% to 6.5% (sound-alikes: "pagar", "paga", "paso", "cola", "corto", "mezcla") | 0.4% to 0.9% ("taller", "shorter", "zoom") |
| Words it listens for, heard as themselves | 81.9% (numbers, and other forms of command words) | 83% ("again") |
| An hour of reading aloud: commands fired in Logic Pro / Pro Tools | 1.0 / 0, none destructive (FLEURS) | 0 / 3.8, none destructive (LibriSpeech) |
| Acts after the word, median | 1.38 s; play, stop, record 0.57 s | 1.10 s; play, stop, record 0.58 s |

What it shows:

- **Spanish words one letter apart.** In the first runs, people's "corte" and "corto" came back
  as "corta" from both recognizers and pressed Cut, and the imperatives "corta", "pega" and
  "elimina" are a vowel from other forms of the same verbs. So Cut, Paste, Delete and Duplicate
  are said alone only as infinitives ("cortar", "pegar", "eliminar", "borrar", "duplicar"), as
  Spanish menus name them, and never run on a near miss.
- **Other forms of a command word are listened for.** Before, "grabado" pressed Record 44
  times in 100, "sola" Solo 82 in 100, "detenido" Stop 33 in 65 and "dividido" Split 51 in 68.
  Voice now listens for such forms (and for "este" and "nada", said alone all the time), so
  they're written down as themselves: 76 and 78 in 100, 60 in 65 and 51 in 68.
- **A sentence can come back all in command words**, because Spanish's include "de", "la" and
  "al": "abrir te garage de al ir al en ese punto" opened an app. In Spanish, "abre ..." and
  "escribe ..." take their words from the open recognizer only.
- **"pagar" is heard as "parar"** (Stop) 13 times in 36. Not destructive, and FLEURS's hour of
  reading never did it.
- **"dos" and "diez" alone** are heard as themselves about half the time ("los", "es"), the other
  numbers 73% to 99%. In "compás dos" the command around them helps; that isn't measured here.
- **Acting takes 0.3 s longer than in English**, because the Spanish model waits longer before
  it ends an utterance. Play, stop and record go the moment they're heard, as in English.

Run it yourself (about 650 MB is read, once: 440 MB of MSWC's 7.4 GB Spanish archive, its
lists, and 90 MB of FLEURS's 2.3 GB):

```sh
pip install vosk==0.3.44 soundfile pytest psutil numpy pyyaml platformdirs
python stress/tools/get_command_words.py /tmp/command-words-es --lang es
python stress/tools/get_fleurs.py /tmp/fleurs-es --lang es_419
VOICE_LANGUAGE=es VOSK_MODEL=/path/to/vosk-model-small-es-0.42 COMMAND_WORDS_DIR=/tmp/command-words-es \
  TALK_DIR=/tmp/fleurs-es python -m pytest stress/test_voice_language.py stress/test_voice_real_speech.py \
  stress/test_command_words.py -v -s
```

### Zoom in Spanish

Limitless Zoom listens in Spanish when Limitless Sound is in Spanish (`ZOOM_LANGUAGE=es` here).
It gets the same checks as in English, from the same Spanish job:

- **Command words:** MSWC's Spanish clips of the words Zoom's commands are said with alone
  ("ampliar", "reducir", "aumentar", "repite", "despierta"...), through Zoom's own gate and
  recognizer (`test_zoom_language.py`). MSWC has nobody saying "acercar", "alejar" or "lupa", so
  "acerca", "aleja" and "ajuste" stand in for the first two and "ajustar", the same verbs with a
  sound less; they should be heard as the command. Then 46 words that sound like a command and
  aren't, or are said all the time: "cerca", "amplia", "reducido", "luna", "otra", "todo".
- **Ordinary talk:** FLEURS's hour of Latin American Spanish read aloud, as Voice hears it
  (`test_zoom_real_speech.py`).
- **Every phrase over music:** each Spanish phrase, the ones of two and more words too, in
  espeak-ng's Latin American voice, with the band from `test_zoom_noise.py` playing under it at
  three loudness levels, and the band alone. Real people's clips only have single words.
- **Vocabulary:** every word Zoom listens for is one the Spanish model knows.

Each run also measures other ways of listening, and every confidence threshold, side by side.
That's how Zoom's Spanish was chosen. What CI measured (ubuntu-latest, October 2026; runs
39918506977, 39919500433 and 39919519719), next to English (the last run's English job):

| | Spanish | English |
|---|---|---|
| Commands said alone, by real people (MSWC) | **89.9% to 91.0%** (189 clips, 7 words) | 91.7% (325 clips: fit, taller, shorter, again) |
| The same verb with a sound less ("acerca" for "acercar") | 72% | |
| Words that aren't commands: zoomed | 12% (46 words, sound-alikes on purpose) | 2.2% (Speech Commands' words) |
| A command other than the one said | 0 | |
| An hour of reading aloud: zoomed | **1, 2 and 1 times** (FLEURS) | 3.8 times (LibriSpeech) |
| Every phrase said over a band, at 30, 15 and 6 dB | 44, 45 and 41 of 45 | all on Linux, 41 of 42 on a Mac |
| The band alone, 2 minutes: zoomed | 0 | at most 1 |

What it shows:

- **The Spanish model writes talk down as commands.** Listening only for Zoom's phrases, as
  English Zoom does, an hour of FLEURS zoomed 81 to 85 times at the same confidence: "zoom dos"
  13 times, "lupa" 7 to 9, "acercar" 5. Nearly every one was heard on its own, with no "[unk]" around it, so the
  sentence rules had nothing to go on; English's model writes such talk down as "[unk]". Zoom
  now listens for the one- and two-letter words and the 300 words said most in Common Voice's
  Spanish too (`apps/zoom/limitless_zoom/common_words.py`), so talk is written down as itself:
  1 to 2 zooms in the hour, from 0.41 and 0.72 sure "disminuir" and "ajustar".
- **The most said words, not the sound-alikes.** Listening for 1000 common words as well
  zoomed 0 times in the hour, but heard 86% of the commands; adding every word that sounds like
  a one-word command ("cerca", "reducido", 159 of them) also 0 times, but only 64% to 66% of the
  commands. Words that close compete with the command itself: "reducir" came back as "seducir"
  or "reducirse", "aumentar" as "comentar". `zoom_words_es.py` has those lists.
- **A command needs 0.15 less confidence in Spanish.** With 325 more words to choose from, the
  recognizer is less sure of the commands it hears right (1 in 20 under 0.64, against about 0.91
  without them). At the default 0.55 it heard 88% of the commands; at 0.40, 90% to 91%, and the
  hour of talk zoomed 1 to 2 times either way.
- **Words that sound like a one-word command still fire it when said alone**: "amplia" Zoom In
  65 times in 100, "reduce" and "reducido" Zoom Out about half the time, "disminuye" and
  "repitió" most of the time. Inside a sentence they don't (the hour of talk), and they're not
  what a musician says alone. English has the same ("bed" is heard as "fit").
- **"aleja" is heard as "deja"** (from "deja de escuchar") 5 times in 11, so "alejar" may be
  weaker than "acercar"; "reducir" (93%) does the same. Nobody in MSWC says "alejar" itself.

Run it yourself, with the Spanish downloads above:

```sh
python stress/tools/get_command_words.py /tmp/zoom-words-es --lang es --zoom
python stress/tools/make_speech.py /tmp/speech-es --zoom es     # needs espeak-ng
ZOOM_LANGUAGE=es VOSK_MODEL=/path/to/vosk-model-small-es-0.42 ZOOM_WORDS_DIR=/tmp/zoom-words-es \
  TALK_DIR=/tmp/fleurs-es TTS_WAV_DIR=/tmp/speech-es python -m pytest stress/test_zoom_language.py \
  stress/test_zoom_real_speech.py stress/test_zoom_noise.py -v -s
```

### Portuguese

Voice in Brazilian Portuguese (`VOICE_LANGUAGE=pt`) gets the same checks, in its own CI job, with
MSWC's Portuguese clips (Common Voice Portuguese, mostly Brazilian) and an hour of FLEURS
Brazilian Portuguese (pt_br). Its stray words are a letter from a command ("sala" and "salvar",
"parte" and "pare", "muita" and "muta") or a command's other meaning ("arma", a weapon). The
command words are the infinitives Voice listens for when a command is said alone; MSWC's
Portuguese has no "mute" or "loop", so the English names aren't measured.

What CI measured, Voice 0.4.2 with Logic Pro in front (runs 39925409575 and 39925513641):

| | Portuguese | Spanish |
|---|---|---|
| Command words right at once | **61.9% to 62.3%** (565 clips, 23 words) | 83.5% to 83.6% |
| At once or with a yes | 62.5% to 62.7% | 84.2% |
| Destructive key from a word not said | 0 | 0 |
| Stray words that fired a command | 5.4% to 6.0% ("sala" heard as "solo" or "salvar") | 6.2% to 6.5% |
| Words it listens for, heard as themselves | 52.5% to 52.6% (numbers, and other forms of command words) | 81.9% |
| An hour of reading aloud: commands fired in Logic Pro / Pro Tools | 1.0 / 1.0, none destructive (FLEURS) | 1.0 / 0 |
| Acts after the word, median | 1.54 s; play, stop, record 0.6 to 0.9 s | 1.38 s; 0.57 s |

**Portuguese is a preview, because of its speech model.** The only small Portuguese model under a
licence the suite can ship is vosk-model-small-pt-0.3, an older model than the Spanish one. It
hears nothing at all in about a third of the clips. A control in CI (runs 39917114601 and
39920195367) ruled out the recordings: the same harness, the same 16 kinds of word (two to ten,
twenty, thirty, "gravar"/"grabar", "parar", "salvar"/"guardar", "solo", "ajuda"/"ayuda"), 25 clips
each:

| | Portuguese model, Portuguese clips | Spanish model, Spanish clips |
|---|---|---|
| Heard nothing at all, as the tests feed a clip (0.5 s of silence before) | 33% | 4% |
| The word itself | 60% | 86% |
| With nothing before / 0.5 s of room noise each side / 1 s each side | 38% / 33% / 32% nothing | 4% / 4% / 5% nothing |
| The clips: loudest, speech length, speech from the start / to the end | -4.6 dBFS, 0.36 s, 0.30 s / 0.33 s | -5.2 dBFS, 0.34 s, 0.31 s / 0.34 s |
| FLEURS read sentences, open recognizer alone, word error rate (100 recordings) | 27.4% | 14.8% |

The clips are alike and padding doesn't change anything, so it's the model; Alpha Cephei's own
list gives it 32.6% word errors on Common Voice's test set. The only other Portuguese model it
lists, FalaBrasil's (1.6 GB), is under the GPL.

What was fixed on the way, from these runs:

- **Words the model doesn't know.** It knows no "mute", "loop", "mixer", "take" or "roll", so
  they're spelled as words it does ("mi ute", "lupi", "mix ser", "tei que", "rol"), and no
  spelling at all of "play", "shift", "tab", "shuffle" or "slip", so those are said in Portuguese.
  It keeps its graph in the model's own folder (no `graph/`), and Voice now finds such a model.
- **Near misses.** Real people's "sala" pressed Save 47 times in 100, "parte" Play, "muita" Mute
  and "copa" Copy, each a letter from a command. Portuguese runs no command on a near miss.
- **Short imperatives.** People's "toca" was right 32% of the time and "tocar" 63%, "volta" 41%
  and "voltar" 63%, "aproxima" 29%. A command said alone is the infinitive, as the menus name it.
- **Sentences.** The command recognizer heard "parar" in "quando você liga para alguém que",
  "dividir" in a sentence about Ebola, "solo" in "polo químicas" and "para" in "se para se": 8
  commands an hour of reading. When the open recognizer heard two words or more without the
  command's, or two more words than it, it's talk. Now 1 an hour, Escape heard in a pause.

Run it yourself (about 500 MB is read, once: 260 MB of MSWC's 1.2 GB Portuguese archive, its
lists, and 90 MB of FLEURS's 2.7 GB):

```sh
python stress/tools/get_command_words.py /tmp/command-words-pt --lang pt
python stress/tools/get_fleurs.py /tmp/fleurs-pt --lang pt_br
VOICE_LANGUAGE=pt VOSK_MODEL=/path/to/vosk-model-small-pt-0.3 COMMAND_WORDS_DIR=/tmp/command-words-pt \
  TALK_DIR=/tmp/fleurs-pt python -m pytest stress/test_voice_language.py stress/test_voice_real_speech.py \
  stress/test_command_words.py -v -s
```

The recordings are not in this repository, and must not be committed. They are all under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Speech Commands: Pete Warden, "Speech Commands: A Dataset for Limited-Vocabulary Speech
  Recognition", 2018. Google.
- LibriSpeech: Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, "LibriSpeech:
  an ASR corpus based on public domain audio books", ICASSP 2015. From LibriVox recordings.
- Multilingual Spoken Words Corpus: MLCommons,
  [mlcommons.org/datasets/multilingual-spoken-words](https://mlcommons.org/datasets/multilingual-spoken-words/);
  Mazumder et al., 2021, NeurIPS Datasets and Benchmarks. Made from Mozilla Common Voice (CC0).
  The English, Spanish and Portuguese clips.
- FLEURS: Alexis Conneau, Min Ma, Simran Khanuja, Yu Zhang, Vera Axelrod, Siddharth Dalmia,
  Jason Riesa, Clara Rivera and Ankur Bapna, "FLEURS: Few-shot Learning Evaluation of Universal
  Representations of Speech", 2022. Google. The Latin American Spanish and the Brazilian Portuguese
  hours.

The speech models aren't in this repository either. The English one is Apache 2.0, and so are
the Spanish one, vosk-model-small-es-0.42, and the Portuguese one, vosk-model-small-pt-0.3 (Alpha
Cephei, alphacephei.com/vosk/models).

None of this replaces a person with a real mic, webcam, controller and DAW. That checklist is in
[HANDOFF.md](../HANDOFF.md).
