"""Offline voice commands with Vosk. Works with any microphone the OS can see,
no internet, no account. Only the zoom phrases are listened for, which makes a
small model accurate even through a laptop mic. In English or Spanish (LANGUAGES):
each has its own speech model and its own phrases (actions.py)."""

import json
import queue
import re
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from array import array
from collections import deque
from pathlib import Path

from . import common_words
from .actions import SPANISH_PHRASES, VOICE_PHRASES
from .words import t

WAKE_ACTIONS = {"wake"}

# Silence isn't decoded. The recognizer was nearly all the CPU Zoom used while waiting:
# decoding every 100 ms of a silent room kept about 5% of a core busy. A block of audio
# counts as sound when it's louder than SOUND, or clearly louder than the quietest the
# microphone has been lately (its noise floor), and never when it's quieter than SILENT.
# A loud room or music always counts, so commands over music are heard exactly as before.
SOUND = 330           # peak level (16-bit) that always counts as sound: -40 dB from full scale
SILENT = 16           # peak level that never does: -66 dB (digital silence, a muted input)
ABOVE_FLOOR = 2.0     # twice the noise floor (+6 dB) counts as sound
FLOOR_RISE = 1.01     # the noise floor follows a room getting louder by about 1 dB a second
PRE_ROLL = 1.0        # seconds from before the first sound that go to the recognizer too, so
                      # the start of a word ("fit", "shorter") is never cut off and it hears
                      # the room just before (quiet speech in a noisy room needs that)
HANG_ON = 1.5         # seconds after the last sound that still go to it: the pause that ends a
                      # command (the model waits 0.5 to 1 s for it), or the next command
RETRY_FIRST, RETRY_MOST = 3, 30   # seconds between tries while the microphone can't be opened
RUN_ON = 0.1   # seconds: a command closer than this to other words was said inside a sentence
MODEL_URL = "https://alphacephei.com/vosk/models/{name}.zip"


class Language:
    """What Zoom listens for in one language, and the speech model that hears it.

    phrases  spoken phrase -> action
    fillers  words people put around a command ("zoom in please", "uh, fit"). The recognizer
             knows them, so they never count as other words around a command, and they're
             ignored. A filler can be two words ("por favor"), ignored only where they come
             together: "por" alone is another word.
    others   words listened for only so that the recognizer can write them down instead of the
             command they sound like; said alone, they do nothing."""

    def __init__(self, code, name, english_name, model, size, phrases, fillers=(), others=()):
        self.code, self.name, self.english_name = code, name, english_name   # "es", "Español", "Spanish"
        self.model, self.size = model, size
        self.phrases = dict(phrases)
        self.fillers = tuple(fillers)
        self.others = tuple(others)
        self.url = MODEL_URL.format(name=model)

    def __repr__(self):
        return f"<Language {self.code}>"

    def adding(self, phrases=None, others=()):
        """The same language with more phrases or other words listened for (the stress tests try
        some)."""
        return Language(self.code, self.name, self.english_name, self.model, self.size,
                        {**self.phrases, **(phrases or {})}, self.fillers, (*self.others, *others))

    def grammar(self):
        """The recognizer's vocabulary: Zoom's phrases, the fillers, the other words, [unk]."""
        return json.dumps(sorted(self.phrases) + list(self.fillers) + list(self.others) + ["[unk]"],
                          ensure_ascii=False)

    def words(self):
        """Every word Zoom listens for in this language."""
        return {w for p in (*self.phrases, *self.fillers, *self.others) for w in p.split()}

    def match(self, text, words, min_conf):
        """Map a recognised utterance to an action, or None.
        words is Vosk's per-word result list with 'conf' scores and times."""
        # "[unk]" is a breath, a click or a word that isn't a command; one before
        # or after a command shouldn't stop it working. But a command said inside a
        # sentence isn't one: two unknown words together, or other words running
        # straight on from it ("...had to see again"). In an hour of people reading
        # aloud, that was nearly everything that zoomed (stress/test_zoom_real_speech.py).
        tokens = without(text.split(), self.fillers)
        if any(a == b == "[unk]" for a, b in zip(tokens, tokens[1:])) or runs_on(words, fillers=self.fillers):
            return None
        action = self.phrases.get(" ".join(w for w in tokens if w != "[unk]"))
        if action is None or self.confidence(words) < min_conf:
            return None
        return action

    def confidence(self, words):
        """How sure the recognizer was of the words in Vosk's per-word result, fillers and [unk]
        left out: the mean of their 'conf' scores (1 when there are none)."""
        words = [w for w in without(words or [], self.fillers) if w.get("word") != "[unk]"]
        return sum(w.get("conf", 1.0) for w in words) / len(words) if words else 1.0

    def first(self, action):
        """The first phrase that does an action: what to suggest saying for it."""
        return next((p for p, a in self.phrases.items() if a == action), None)

    def by_action(self):
        """{action: [its phrases]}, in the order they're written."""
        out = {}
        for phrase, action in self.phrases.items():
            out.setdefault(action, []).append(phrase)
        return out


ENGLISH = Language("en", "English", "English", "vosk-model-small-en-us-0.15", "40 MB", VOICE_PHRASES,
                   fillers=("please", "thanks", "okay", "um", "uh"))
# vosk-model-small-es-0.42, Apache 2.0 (Alpha Cephei): the same model Limitless Voice uses for
# Spanish, so a computer that has it for Voice already has it for Zoom (app.py looks there).
# It also listens for the words said most in Spanish (common_words.py): without them, the model
# writes down ordinary talk as the nearest command.
SPANISH = Language("es", "Español", "Spanish", "vosk-model-small-es-0.42", "39 MB", SPANISH_PHRASES,
                   fillers=("por favor", "gracias"), others=common_words.SPANISH)
LANGUAGES = {lang.code: lang for lang in (ENGLISH, SPANISH)}

# English, as Zoom always listened (the stress tests use these).
MODEL_NAME = ENGLISH.model
FILLERS = ENGLISH.fillers


def without(items, fillers):
    """Words (or Vosk's per-word results) without the fillers among them: a filler of two words
    only where the two come together."""
    fillers = sorted((f.split() for f in fillers), key=len, reverse=True)
    out, i = [], 0
    while i < len(items):
        n = next((len(f) for f in fillers if [x.get("word") if isinstance(x, dict) else x
                                              for x in items[i:i + len(f)]] == f), 0)
        if n:
            i += n
        else:
            out.append(items[i])
            i += 1
    return out


def runs_on(words, gap=RUN_ON, fillers=ENGLISH.fillers):
    """Whether the command in Vosk's per-word result runs straight on from other words, with less
    than gap seconds between: said inside a sentence, not on its own. Vosk times every word,
    unknown ones too."""
    words = without(words or [], fillers)
    known = [i for i, w in enumerate(words) if w.get("word") != "[unk]"]
    if not known or "start" not in words[known[0]]:
        return False
    first, last = words[known[0]], words[known[-1]]
    before = [w for w in words[:known[0]] if w.get("word") == "[unk]"]
    after = [w for w in words[known[-1] + 1:] if w.get("word") == "[unk]"]
    return bool(before and first["start"] - before[-1]["end"] < gap
                or after and after[0]["start"] - last["end"] < gap)


def match_phrase(text, words, min_conf, language=ENGLISH):
    """Map a recognised utterance to an action, or None (see Language.match)."""
    return language.match(text, words, min_conf)


def grammar(language=ENGLISH):
    return language.grammar()


def model_language(path):
    """The language a Vosk model folder is for, from its name ("vosk-model-small-es-0.42" is
    Spanish); None when the name doesn't say."""
    m = re.match(r"vosk-model-(?:small-)?([a-z]{2})(?:[-_]|$)", Path(path).name.lower())
    return m.group(1) if m else None


def is_model(folder):
    return (Path(folder) / "am").is_dir() or (Path(folder) / "conf").is_dir()


def find_model(configured, search_dirs, language=ENGLISH):
    """The language's speech model: the folder chosen in settings when it's for this language
    (a folder whose name doesn't say is taken to be English, as it always was), else the
    language's model in the first of search_dirs that has it."""
    candidates = []
    if configured and (model_language(configured) or "en") == language.code:
        candidates.append(Path(configured))
    candidates += [Path(d) / language.model for d in search_dirs]
    for c in candidates:
        if is_model(c):
            return c
    return None


def download_model(dest_dir, progress=None, language=ENGLISH, timeout=30):
    """Download the language's model and unpack it into dest_dir. It's unpacked beside its final
    place and moved there once whole, so a download cut off half way is never taken for a model."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest_dir, prefix=".download-") as tmp:
        zpath = Path(tmp) / f"{language.model}.zip"
        with urllib.request.urlopen(language.url, timeout=timeout) as resp, open(zpath, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(1.0, done / total))
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        dest = dest_dir / language.model
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(Path(tmp) / language.model), str(dest))
    return dest


def list_microphones():
    import sounddevice as sd

    names = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in names:
            names.append(d["name"])
    return names


def pick_channel(data, channels):
    """Mono int16 audio from interleaved int16 audio: the loudest channel.
    On an audio interface the mic is often on input 2, not input 1."""
    samples = array("h")
    samples.frombytes(data)
    if channels == 1:
        return samples
    best, best_energy = None, -1
    for c in range(channels):
        ch = samples[c::channels]
        energy = sum(map(abs, ch[::8]))
        if energy > best_energy:
            best, best_energy = ch, energy
    return best


def peak(samples):
    """The loudest sample of a block (every fourth one is plenty)."""
    return max(map(abs, samples[::4]), default=0)


class SpeechGate:
    """Decides which blocks of microphone audio the recognizer hears: nothing while it's
    quiet; when a sound starts, the second before it, then everything until a second and a
    half after the last sound."""

    def __init__(self, block_seconds=0.1):
        self.before = deque(maxlen=max(1, round(PRE_ROLL / block_seconds)))
        self.hang_on = max(1, round(HANG_ON / block_seconds))
        self.floor = float(SOUND)
        self.left = 0   # blocks still to pass on after the last sound; 0 means it's quiet

    def is_sound(self, loudest):
        sound = loudest >= SILENT and (loudest >= SOUND or loudest >= self.floor * ABOVE_FLOOR)
        self.floor = min(float(loudest), max(self.floor * FLOOR_RISE, self.floor + 1))
        return sound

    def push(self, block, loudest):
        """The blocks for the recognizer now (oldest first), and True when a sound just
        ended, so whatever the recognizer heard should be read out."""
        if self.is_sound(loudest):
            blocks = [*self.before, block]
            self.before.clear()
            self.left = self.hang_on
            return blocks, False
        if self.left:
            self.left -= 1
            return [block], self.left == 0
        self.before.append(block)
        return [], False


class Hearing:
    """Microphone audio in, the recognizer's results out (dicts with "text" and "result"),
    with silence skipped by a SpeechGate. The same for the microphone and for recordings."""

    def __init__(self, rec, on_result, block_seconds=0.1):
        self.rec, self.on_result = rec, on_result
        self.gate = SpeechGate(block_seconds)

    def hear(self, samples, loudest=None):
        blocks, ended = self.gate.push(samples, peak(samples) if loudest is None else loudest)
        for b in blocks:
            if self.rec.AcceptWaveform(b.tobytes()):
                self.on_result(json.loads(self.rec.Result()))
        if ended:
            # The recognizer has nearly always finished the command by itself in the pause.
            # If it still holds words, read them out now. Otherwise leave it be: finishing
            # starts it afresh, and it would forget what it has learned about this
            # microphone and room, which quiet speech in a noisy room needs.
            partial = json.loads(self.rec.PartialResult()).get("partial", "")
            if any(w != "[unk]" for w in partial.split()):
                self.finish()

    def finish(self):
        """Read out anything heard that the recognizer hasn't finished with yet."""
        self.on_result(json.loads(self.rec.FinalResult()))


class VoiceListener(threading.Thread):
    """Runs in the background and calls on_action(action) for each command heard.
    on_status(text) reports problems and state in plain words, on_heard(text)
    gets every phrase understood, and on_level(0-1) the microphone loudness."""

    def __init__(self, model_path, on_action, on_status, device=None, min_conf=0.55,
                 on_heard=None, on_level=None, language=ENGLISH):
        super().__init__(daemon=True)
        self.model_path, self.device, self.min_conf = model_path, device, min_conf
        self.language = language   # the phrases listened for, in the model's language
        self.on_action, self.on_status = on_action, on_status
        self.on_heard = on_heard or (lambda text: None)
        self.on_level = on_level or (lambda value: None)
        self.asleep = False
        self._halt = threading.Event()
        # The last status and meter step passed on. Repeats aren't sent: each one wakes the
        # app's windows to show nothing new.
        self._said = None
        self._meter = None
        self._retry = RETRY_FIRST
        self._recognizer = None   # (sample rate, recognizer), kept from one try to the next

    def stop(self):
        self._halt.set()

    def _status(self, text):
        if text != self._said:
            self._said = text
            self.on_status(text)

    def run(self):
        try:
            import sounddevice as sd
            import vosk

            vosk.SetLogLevel(-1)
            model = vosk.Model(str(self.model_path))
        except Exception as e:
            self._status(t("Voice couldn't start: {problem}", problem=e))
            return

        while not self._halt.is_set():
            try:
                self._listen(sd, vosk, model)
            except Exception as e:
                # Microphone unplugged, busy or missing: say so, then keep trying, less often
                # the longer it lasts.
                self._status(t("Microphone problem: {problem}. Retrying.", problem=e))
                self._halt.wait(self._retry)
                self._retry = min(RETRY_MOST, self._retry * 2)

    def _listen(self, sd, vosk, model):
        info = sd.query_devices(self.device, "input")
        rate = int(info["default_samplerate"])
        channels = max(1, min(2, int(info["max_input_channels"])))
        audio = queue.Queue()

        def callback(data, frames, t, status):
            audio.put(bytes(data))

        with sd.RawInputStream(samplerate=rate, blocksize=rate // 10, device=self.device,
                               dtype="int16", channels=channels, callback=callback) as stream:
            # Made once the microphone is open, and kept: building one takes a while.
            if self._recognizer is None or self._recognizer[0] != rate:
                rec = vosk.KaldiRecognizer(model, rate, self.language.grammar())
                rec.SetWords(True)
                self._recognizer = (rate, rec)
            hearing = Hearing(self._recognizer[1], self._result)
            self._retry = RETRY_FIRST
            self._status(t("Listening on {name}", name=info["name"]))
            while not self._halt.is_set():
                try:
                    data = audio.get(timeout=0.5)
                except queue.Empty:
                    if not stream.active:
                        raise RuntimeError("the microphone stopped sending sound")
                    continue
                mono = pick_channel(data, channels)
                loudest = peak(mono)
                meter = min(100, loudest * 100 // 20000)
                if meter != self._meter:
                    self._meter = meter
                    self.on_level(meter / 100)
                hearing.hear(mono, loudest)

    def _result(self, res):
        text = " ".join(res.get("text", "").replace("[unk]", "").split())
        action = self.language.match(res.get("text", ""), res.get("result"), self.min_conf)
        if text:
            self.on_heard(text if action else t("{heard} (not sure, ignored)", heard=text))
        if action is None:
            return
        if self.asleep and action not in WAKE_ACTIONS:
            return
        if action == "sleep":
            self.asleep = True
        elif action == "wake":
            self.asleep = False
        self.on_action(action)


def recognize_file(model_path, wav_path, min_conf=0.55, model=None, language=ENGLISH):
    """Run a 16-bit WAV recording through the same recogniser the way the microphone's audio
    goes, in 100 ms blocks with silence skipped. Returns the text and action of the last
    thing heard. Used to test voice in CI. Pass a loaded vosk.Model to skip loading it, and
    the Language the model is for."""
    import wave

    import vosk

    vosk.SetLogLevel(-1)
    heard = []
    with wave.open(str(wav_path), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        rec = vosk.KaldiRecognizer(model or vosk.Model(str(model_path)), rate, language.grammar())
        rec.SetWords(True)
        hearing = Hearing(rec, heard.append)
        while True:
            data = w.readframes(rate // 10)
            if not data:
                break
            hearing.hear(pick_channel(data, channels))
        hearing.finish()
    res = next((r for r in reversed(heard) if r.get("text")), {})
    return res.get("text", ""), language.match(res.get("text", ""), res.get("result"), min_conf)
