"""Offline voice commands with Vosk. Works with any microphone the OS can see,
no internet, no account. Only the zoom phrases are listened for, which makes a
small model accurate even through a laptop mic."""

import json
import queue
import threading
import urllib.request
import zipfile
from array import array
from pathlib import Path

from .actions import VOICE_PHRASES

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
WAKE_ACTIONS = {"wake"}


def match_phrase(text, words, min_conf):
    """Map a recognised utterance to an action, or None.
    words is Vosk's per-word result list with 'conf' scores."""
    # "[unk]" is a breath, a click or a word that isn't a command; one before
    # or after a command shouldn't stop it working.
    text = " ".join(w for w in text.split() if w != "[unk]")
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
        energy = sum(abs(x) for x in ch[::8])
        if energy > best_energy:
            best, best_energy = ch, energy
    return best


def level(samples):
    """0-1 loudness of a block, for the microphone meter."""
    if not samples:
        return 0.0
    peak = max(abs(x) for x in samples[::4])
    return min(1.0, peak / 20000)


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

    def stop(self):
        self._halt.set()

    def run(self):
        try:
            import sounddevice as sd
            import vosk

            vosk.SetLogLevel(-1)
            model = vosk.Model(str(self.model_path))
        except Exception as e:
            self.on_status(f"Voice couldn't start: {e}")
            return

        while not self._halt.is_set():
            try:
                self._listen(sd, vosk, model)
            except Exception as e:
                # Microphone unplugged or busy: say so, then keep retrying.
                self.on_status(f"Microphone problem: {e}. Retrying.")
                self._halt.wait(3)

    def _listen(self, sd, vosk, model):
        info = sd.query_devices(self.device, "input")
        rate = int(info["default_samplerate"])
        channels = max(1, min(2, int(info["max_input_channels"])))
        rec = vosk.KaldiRecognizer(model, rate, grammar())
        rec.SetWords(True)
        audio = queue.Queue()

        def callback(data, frames, t, status):
            audio.put(bytes(data))

        with sd.RawInputStream(samplerate=rate, blocksize=rate // 10, device=self.device,
                               dtype="int16", channels=channels, callback=callback):
            self.on_status(f"Listening on {info['name']}")
            while not self._halt.is_set():
                try:
                    data = audio.get(timeout=0.5)
                except queue.Empty:
                    continue
                mono = pick_channel(data, channels)
                self.on_level(level(mono))
                if rec.AcceptWaveform(mono.tobytes()):
                    res = json.loads(rec.Result())
                    text = " ".join(res.get("text", "").replace("[unk]", "").split())
                    action = match_phrase(res.get("text", ""), res.get("result"), self.min_conf)
                    if text:
                        self.on_heard(text if action else f"{text} (not sure, ignored)")
                    if action is None:
                        continue
                    if self.asleep and action not in WAKE_ACTIONS:
                        continue
                    if action == "sleep":
                        self.asleep = True
                    elif action == "wake":
                        self.asleep = False
                    self.on_action(action)


def recognize_file(model_path, wav_path, min_conf=0.55):
    """Run a WAV recording through the same recogniser. Used to test voice in CI."""
    import wave

    import vosk

    vosk.SetLogLevel(-1)
    with wave.open(str(wav_path), "rb") as w:
        rec = vosk.KaldiRecognizer(vosk.Model(str(model_path)), w.getframerate(), grammar())
        rec.SetWords(True)
        while True:
            data = w.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
    res = json.loads(rec.FinalResult())
    return res.get("text", ""), match_phrase(res.get("text", ""), res.get("result"), min_conf)
