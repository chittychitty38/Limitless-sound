"""Offline voice commands with Vosk. Works with any microphone the OS can see,
no internet, no account. Only the zoom phrases are listened for, which makes a
small model accurate even through a laptop mic."""

import json
import queue
import threading
import urllib.request
import zipfile
from array import array
from collections import deque
from pathlib import Path

from .actions import VOICE_PHRASES

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
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


def match_phrase(text, words, min_conf):
    """Map a recognised utterance to an action, or None.
    words is Vosk's per-word result list with 'conf' scores."""
    # "[unk]" is a breath, a click or a word that isn't a command; one before
    # or after a command shouldn't stop it working. Two together are words: the
    # command was part of a sentence. In an hour of people reading aloud, more than
    # half of what zoomed was ("[unk] [unk] again [unk]", stress/test_zoom_real_speech.py).
    tokens = text.split()
    if any(a == b == "[unk]" for a, b in zip(tokens, tokens[1:])):
        return None
    text = " ".join(w for w in tokens if w != "[unk]")
    action = VOICE_PHRASES.get(text)
    if action is None:
        return None
    words = [w for w in (words or []) if w.get("word") != "[unk]"]
    if words:
        conf = sum(w.get("conf", 1.0) for w in words) / len(words)
        if conf < min_conf:
            return None
    return action


def grammar():
    vocab = sorted(VOICE_PHRASES)
    return json.dumps(vocab + ["[unk]"])


def find_model(configured, search_dirs):
    candidates = [Path(configured)] if configured else []
    candidates += [Path(d) / MODEL_NAME for d in search_dirs]
    for c in candidates:
        if (c / "am").is_dir() or (c / "conf").is_dir():
            return c
    return None


def download_model(dest_dir, progress=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zpath = dest_dir / f"{MODEL_NAME}.zip"

    def hook(blocks, bsize, total):
        if progress and total > 0:
            progress(min(1.0, blocks * bsize / total))

    urllib.request.urlretrieve(MODEL_URL, zpath, hook)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest_dir)
    zpath.unlink()
    return dest_dir / MODEL_NAME


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
                 on_heard=None, on_level=None):
        super().__init__(daemon=True)
        self.model_path, self.device, self.min_conf = model_path, device, min_conf
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
            self._status(f"Voice couldn't start: {e}")
            return

        while not self._halt.is_set():
            try:
                self._listen(sd, vosk, model)
            except Exception as e:
                # Microphone unplugged, busy or missing: say so, then keep trying, less often
                # the longer it lasts.
                self._status(f"Microphone problem: {e}. Retrying.")
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
                rec = vosk.KaldiRecognizer(model, rate, grammar())
                rec.SetWords(True)
                self._recognizer = (rate, rec)
            hearing = Hearing(self._recognizer[1], self._result)
            self._retry = RETRY_FIRST
            self._status(f"Listening on {info['name']}")
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
        action = match_phrase(res.get("text", ""), res.get("result"), self.min_conf)
        if text:
            self.on_heard(text if action else f"{text} (not sure, ignored)")
        if action is None:
            return
        if self.asleep and action not in WAKE_ACTIONS:
            return
        if action == "sleep":
            self.asleep = True
        elif action == "wake":
            self.asleep = False
        self.on_action(action)


def recognize_file(model_path, wav_path, min_conf=0.55, model=None):
    """Run a 16-bit WAV recording through the same recogniser the way the microphone's audio
    goes, in 100 ms blocks with silence skipped. Returns the text and action of the last
    thing heard. Used to test voice in CI. Pass a loaded vosk.Model to skip loading it."""
    import wave

    import vosk

    vosk.SetLogLevel(-1)
    heard = []
    with wave.open(str(wav_path), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        rec = vosk.KaldiRecognizer(model or vosk.Model(str(model_path)), rate, grammar())
        rec.SetWords(True)
        hearing = Hearing(rec, heard.append)
        while True:
            data = w.readframes(rate // 10)
            if not data:
                break
            hearing.hear(pick_channel(data, channels))
        hearing.finish()
    res = next((r for r in reversed(heard) if r.get("text")), {})
    return res.get("text", ""), match_phrase(res.get("text", ""), res.get("result"), min_conf)
