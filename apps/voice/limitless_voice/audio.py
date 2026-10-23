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
from collections import deque
from dataclasses import dataclass

from .words import ui


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


# Silence isn't decoded. Both recognizers decoding every 100 ms of a quiet room kept about 6% of
# a core busy, all the time Voice was listening (measured on CI runners, October 2026; more on an
# older laptop). This is Limitless Zoom's gate (apps/zoom/limitless_zoom/voice.py): a block counts
# as sound when it's louder than SOUND, or clearly louder than the quietest the microphone has
# been lately (its noise floor), and never when it's quieter than SILENT. A loud room or music
# always counts, so commands over music are heard exactly as before.
SOUND = 330           # peak level (16-bit) that always counts as sound: -40 dB from full scale
SILENT = 16           # peak level that never does: -66 dB (digital silence, a muted input)
ABOVE_FLOOR = 2.0     # twice the noise floor (+6 dB) counts as sound
FLOOR_RISE = 1.01     # the noise floor follows a room getting louder by about 1 dB a second
PRE_ROLL = 1.0        # seconds from before the first sound that go to the recognizers too, so the
                      # start of a word is never cut off and they hear the room just before
HANG_ON = 1.5         # seconds after the last sound that still go to them: the quiet that ends an
                      # utterance (the open recognizer waits up to a second for it)


def peak(pcm):
    """The loudest sample of a block of 16-bit audio (every fourth one is plenty)."""
    samples = array.array("h")
    samples.frombytes(pcm)
    return max(map(abs, samples[::4]), default=0)


class SpeechGate:
    """Decides which blocks of microphone audio the recognizers hear: nothing while it's quiet;
    when a sound starts, the second before it, then everything until a second and a half after
    the last sound."""

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
        """The blocks for the recognizers now (oldest first), and True when a sound just ended."""
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


def build_grammar(phrases):
    """The command recognizer's phrase list. [unk] soaks up everything else. Only words: letters
    in any language ("compás"), digits, apostrophes and spaces."""
    return sorted(p for p in phrases if p and all(c.isalnum() or c in " '" for c in p)) + ["[unk]"]


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
        self._gate = SpeechGate()

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
        self._gate = SpeechGate()
        recs = {"open": vosk.KaldiRecognizer(model, rate)}
        if self.use_command_vocabulary:
            # As UTF-8: Vosk reads "comp\u00e1s" as those letters, not as "compás"
            grammar = json.dumps(build_grammar(self.phrases), ensure_ascii=False)
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
                    self.on_error(ui.text("Lost that microphone ({error}). Switched to the default one.", error=e))
                else:
                    self.on_error(ui.text("Microphone problem: {error}. Retrying…", error=e))
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
                    self._gate = SpeechGate()
                    was_paused = False
                self.hear(recs, data)

    def hear(self, recs, data):
        """One block from the microphone, through the silence gate to the recognizers."""
        blocks, ended = self._gate.push(data, peak(data))
        for block in blocks:
            self._feed(recs, block)
        if ended:
            self._finish(recs)

    def _finish(self, recs):
        """The sound has stopped: read out anything the recognizers still hold. They nearly
        always end the utterance by themselves in the quiet after it. If they hold nothing,
        they're left be: finishing starts them afresh, and they'd forget what they've learned
        about this microphone and room."""
        held = json.loads(recs["open"].PartialResult()).get("partial", "")
        if "commands" in recs:
            held += " " + " ".join(self._cmd_parts)
            held += " " + json.loads(recs["commands"].PartialResult()).get("partial", "")
        if held.replace("[unk]", "").strip():
            self._end(recs, json.loads(recs["open"].FinalResult()).get("text", ""))

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
        if recs["open"].AcceptWaveform(data):
            self._end(recs, json.loads(recs["open"].Result()).get("text", ""))

    def _end(self, recs, open_text):
        """The open recognizer has ended an utterance: report it with the command recognizer's."""
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
