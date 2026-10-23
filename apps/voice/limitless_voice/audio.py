"""Microphone input and speech recognition.

Works with whatever microphone the computer has: built-in, USB, a headset or
an audio interface. We open the mic at its own sample rate (Vosk resamples
internally), so devices that only do 44.1 or 48 kHz are fine.

Each chunk of audio goes to two recognizers at once:
  commands  limited to the words our commands use. Far more accurate on
            cheap mics and in noisy rooms, because it can't drift into
            unrelated words ("record" never turns into "manicured").
  open      the full English vocabulary, for dictation and for commands
            that take free text ("type ...", "open ...").
"""

import array
import json
import math
import queue
import threading
from dataclasses import dataclass



@dataclass
class Device:
    index: int
    name: str
    default_rate: int
    is_default: bool


def list_input_devices():
    """Input devices, one entry per physical mic (no duplicates across host APIs)."""
    import sounddevice as sd
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    host_apis = sd.query_hostapis()
    # On Windows the same mic shows up under MME, DirectSound, WASAPI and WDM-KS.
    # Prefer WASAPI (modern, accurate names), else whatever the default device uses.
    preferred = None
    for i, api in enumerate(host_apis):
        if "WASAPI" in api["name"]:
            preferred = i
    if preferred is None and default_in is not None and default_in >= 0:
        preferred = sd.query_devices(default_in)["hostapi"]
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        if preferred is not None and d["hostapi"] != preferred:
            continue
        devices.append(Device(i, d["name"], int(d["default_samplerate"]), i == default_in))
    if not devices and default_in is not None and default_in >= 0:
        d = sd.query_devices(default_in)
        devices.append(Device(default_in, d["name"], int(d["default_samplerate"]), True))
    return devices


def level_of(pcm):
    """Loudness of a chunk of 16-bit audio, scaled to 0..1 for a meter."""
    samples = array.array("h", pcm)
    if not samples:
        return 0.0
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
    return min(1.0, rms * 8)


# How long the command recognizer must hear nothing new after an instant command (play, stop,
# record) before it's reported. Waiting for the utterance to end takes a second or more: people
# reading words aloud were heard a median 1.1 s after the word ended (stress/test_voice_real_speech.py).
INSTANT_AFTER = 0.3


def build_grammar(phrases):
    """The command recognizer's phrase list. [unk] soaks up everything else."""
    return sorted(p for p in phrases if p and p.isascii()) + ["[unk]"]


class Listener:
    """Reads the mic on a background thread and reports what was said.

    on_text(command_transcript, open_transcript)   one finished utterance
    on_level(0.0..1.0)                              about 10 times a second
    on_error(message)                               mic lost or failed; we keep retrying
    instant(command_transcript) -> bool             optional: a command to report the moment the
                                                    command recognizer has heard just that, with
                                                    nothing new for INSTANT_AFTER seconds, rather
                                                    than at the end of the utterance
    """

    def __init__(self, model_path, phrases, on_text, on_level=None, on_error=None,
                 device=None, use_command_vocabulary=True, instant=None):
        self.model_path = model_path
        self.phrases = phrases
        self.on_text = on_text
        self.on_level = on_level or (lambda level: None)
        self.on_error = on_error or (lambda msg: None)
        self.device = device
        self.use_command_vocabulary = use_command_vocabulary
        self._model = None
        self._thread = None
        self._stop = threading.Event()
        self._audio = queue.Queue(maxsize=200)
        self._cmd_parts = []
        self._rebuild = False
        self.paused = False
        self.instant = instant
        self._steady = ("", 0.0)   # the command recognizer's words so far, and for how long
        self._early = False        # this utterance's command has been reported already
        self._rate = 16000

    # -- lifecycle -------------------------------------------------------

    def load_model(self):
        import vosk
        vosk.SetLogLevel(-1)
        if self._model is None:
            self._model = vosk.Model(str(self.model_path))
        return self._model

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mic", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def set_device(self, device):
        self.device = device
        if self._thread:
            self.stop()
            self.start()

    def set_phrases(self, phrases):
        """New command phrases take effect at the next audio chunk, without reopening the mic."""
        self.phrases = phrases
        self._rebuild = True

    # -- worker ----------------------------------------------------------

    def _make_recognizers(self, rate):
        import vosk
        model = self.load_model()
        self._rate = rate
        recs = {"open": vosk.KaldiRecognizer(model, rate)}
        if self.use_command_vocabulary:
            grammar = json.dumps(build_grammar(self.phrases))
            recs["commands"] = vosk.KaldiRecognizer(model, rate, grammar)
        return recs

    def _run(self):
        import sounddevice as sd
        failures = 0
        while not self._stop.is_set():
            try:
                self._listen_once(sd)
                failures = 0
            except Exception as e:  # mic unplugged, busy, or refused
                if self._stop.is_set():
                    break
                failures += 1
                self.on_level(0.0)
                if failures >= 2 and self.device is not None:
                    # the chosen mic is gone; carry on with the system default
                    self.device = None
                    self.on_error(f"Lost that microphone ({e}). Switched to the default one.")
                else:
                    self.on_error(f"Microphone problem: {e}. Retrying…")
                self._stop.wait(min(2 ** failures, 10))

    def _listen_once(self, sd):
        info = sd.query_devices(self.device, "input")
        rate = int(info["default_samplerate"]) or 16000
        self._rebuild = False
        recs = self._make_recognizers(rate)
        block = int(rate * 0.1)

        def callback(indata, frames, t, status):
            try:
                self._audio.put_nowait(bytes(indata))
            except queue.Full:
                pass  # recognizer fell behind; dropping is better than lagging

        with sd.RawInputStream(samplerate=rate, blocksize=block, device=self.device,
                               dtype="int16", channels=1, callback=callback):
            self.on_error("")  # clear any previous error
            was_paused = False
            while not self._stop.is_set():
                try:
                    data = self._audio.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.on_level(level_of(data))
                if self._rebuild:
                    # the phrase list changed (an app joined or left the suite)
                    self._rebuild = False
                    recs = self._make_recognizers(rate)
                    self._forget()
                if self.paused:
                    was_paused = True
                    continue
                if was_paused:
                    # forget anything half-heard while we were talking
                    for rec in recs.values():
                        rec.Reset()
                    self._forget()
                    was_paused = False
                self._feed(recs, data)

    def _forget(self):
        self._cmd_parts = []
        self._steady = ("", 0.0)
        self._early = False

    def _feed(self, recs, data):
        # The command recognizer may end a phrase a moment before the open
        # one does; keep its pieces until the open recognizer says the
        # utterance is over, then report both transcripts together. An
        # instant command goes as soon as it's heard (_check_instant).
        if "commands" in recs:
            if recs["commands"].AcceptWaveform(data):
                self._cmd_parts.append(json.loads(recs["commands"].Result()).get("text", ""))
                self._steady = ("", 0.0)
                self._check_instant(recs, " ".join(p for p in self._cmd_parts if p).strip(), ended=True)
            elif self.instant is not None:
                partial = json.loads(recs["commands"].PartialResult()).get("partial", "")
                words = " ".join(p for p in self._cmd_parts + [partial] if p).strip()
                said, held = self._steady
                held = held + len(data) / 2 / self._rate if words == said else 0.0
                self._steady = (words, held)
                if held >= INSTANT_AFTER - 1e-6:
                    self._check_instant(recs, words)
        if not recs["open"].AcceptWaveform(data):
            return
        open_text = json.loads(recs["open"].Result()).get("text", "")
        cmd_text = ""
        if "commands" in recs:
            self._cmd_parts.append(json.loads(recs["commands"].FinalResult()).get("text", ""))
            recs["commands"].Reset()
            cmd_text = " ".join(p for p in self._cmd_parts if p).strip()
        early = self._early
        self._forget()
        if early and not cmd_text.replace("[unk]", "").strip():
            return   # its command went already, and nothing else was said that could be one
        if open_text or cmd_text.replace("[unk]", "").strip():
            self.on_text(cmd_text or open_text, open_text)

    def _check_instant(self, recs, words, ended=False):
        """Report an instant command (play, stop, record) now, with the open recognizer's words
        so far, then start the command recognizer afresh for whatever comes next."""
        if self.instant is None or not words or not self.instant(words):
            return
        so_far = json.loads(recs["open"].PartialResult()).get("partial", "")
        self.on_text(words, so_far)
        if not ended:
            recs["commands"].Reset()
        self._cmd_parts = []
        self._steady = ("", 0.0)
        self._early = True
