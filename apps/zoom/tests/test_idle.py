"""Limitless Zoom waiting quietly: with nobody speaking and nothing pressed, nothing decodes,
redraws or ticks fast. Zoom 0.1.1 used 5.6 to 6.8% of a core sitting idle on a fresh Intel
Mac (the nightly proof); these are the things that did it, or could have."""
import json
import os
import random
import sys
import threading
import time
import types
from array import array

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from limitless_zoom import voice
from limitless_zoom.app import ZoomApp, single_instance
from limitless_zoom.settings import Settings
from limitless_zoom.suite import actions
from test_ui import PermBackend, hover, make_app

RATE = 48000
BLOCK = RATE // 10   # the microphone's 100 ms blocks


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def tone(peak_level, n=BLOCK, seed=0):
    rng = random.Random(seed)
    return array("h", [int(rng.uniform(-peak_level, peak_level)) for _ in range(n)])


def noise(rms, n=BLOCK, seed=0):
    rng = random.Random(seed)
    return array("h", [max(-32768, min(32767, int(rng.gauss(0, rms)))) for _ in range(n)])


class FakeRecognizer:
    def __init__(self, *args):
        self.fed = []
        self.finals = 0
        self.partial = ""   # what it's still holding, not yet a result

    def SetWords(self, on):
        pass

    def AcceptWaveform(self, data):
        self.fed.append(data)
        return False

    def Result(self):
        return '{"text": ""}'

    def PartialResult(self):
        return json.dumps({"partial": self.partial})

    def FinalResult(self):
        self.finals += 1
        self.partial = ""
        return '{"text": ""}'


# The silence gate ---------------------------------------------------------------

def test_silence_never_reaches_the_recognizer():
    """A minute of digital silence (no microphone permission yet, a muted input) and a minute
    of a quiet room (-60 dB) cost the recognizer nothing. Zoom 0.1.1 decoded all of it."""
    zeros = [array("h", [0]) * BLOCK]
    room = [noise(33, seed=i) for i in range(20)]
    for blocks in (zeros, room):
        rec = FakeRecognizer()
        h = voice.Hearing(rec, lambda r: None)
        for i in range(600):
            h.hear(blocks[i % len(blocks)])
        assert rec.fed == [] and rec.finals == 0


def test_a_command_gets_the_second_before_it_and_the_pause_after():
    rec = FakeRecognizer()
    h = voice.Hearing(rec, lambda r: None)
    quiet = [noise(10, seed=i) for i in range(20)]
    for q in quiet:
        h.hear(q)
    assert rec.fed == []
    word = tone(8000)
    h.hear(word)
    # the ten blocks just before the word (its quiet start and the room), then the word itself
    assert rec.fed == [q.tobytes() for q in quiet[-10:]] + [word.tobytes()]
    for i in range(14):
        h.hear(noise(10, seed=100 + i))
    assert len(rec.fed) == 11 + 14   # still listening for the pause and what comes next
    h.hear(noise(10, seed=200))
    assert len(rec.fed) == 26        # 1.5 s after the last sound it stops
    assert rec.finals == 0           # the recognizer had finished: left as it is
    for i in range(50):
        h.hear(noise(10, seed=300 + i))
    assert len(rec.fed) == 26

    # A sound the recognizer is still making words of when listening stops: read out now.
    h.hear(word)
    rec.partial = "[unk] zoom"
    for i in range(15):
        h.hear(noise(10, seed=400 + i))
    assert rec.finals == 1
    # Only a cough or a click ("[unk]") held: nothing to read out.
    h.hear(word)
    rec.partial = "[unk]"
    for i in range(15):
        h.hear(noise(10, seed=500 + i))
    assert rec.finals == 1


def test_loud_room_and_music_are_always_heard():
    """Above -40 dB every block is decoded, as before: commands over music still work."""
    rec = FakeRecognizer()
    h = voice.Hearing(rec, lambda r: None)
    for i in range(100):
        h.hear(tone(400 + (i % 7) * 50, seed=i))
    assert len(rec.fed) == 100


def test_quiet_speech_through_a_quiet_interface_is_heard():
    """An interface with low gain: noise at -80 dB, speech peaking at -50 dB."""
    rec = FakeRecognizer()
    h = voice.Hearing(rec, lambda r: None)
    for i in range(30):
        h.hear(tone(3, seed=i))
    assert rec.fed == []
    h.hear(tone(100))
    assert len(rec.fed) == 11


# The listener, with a fake microphone ---------------------------------------------

class FakeVosk(types.SimpleNamespace):
    def __init__(self):
        super().__init__(made=[])

    def KaldiRecognizer(self, model, rate, grammar):
        rec = FakeRecognizer()
        self.made.append(rate)
        return rec

    def Model(self, path):
        return object()

    def SetLogLevel(self, level):
        pass


class FakeMic:
    """sounddevice with one microphone that sends the given blocks, then goes quiet
    (or stops altogether, like an unplugged USB mic, with dies=True)."""

    def __init__(self, blocks=(), fail=None, dies=False):
        self.blocks, self.fail, self.dies = list(blocks), fail, dies
        self.queried = []
        self.opened = 0

    def query_devices(self, device=None, kind=None):
        self.queried.append(time.monotonic())
        if self.fail:
            raise RuntimeError(self.fail)
        return {"name": "Fake Mic", "default_samplerate": RATE, "max_input_channels": 1}

    def RawInputStream(self, samplerate, blocksize, device, dtype, channels, callback):
        mic = self
        mic.opened += 1

        class Stream:
            active = True

            def __enter__(self):
                def play():
                    for b in mic.blocks:
                        callback(b.tobytes(), len(b), None, None)
                    if mic.dies:
                        Stream.active = False
                threading.Thread(target=play, daemon=True).start()
                return self

            def __exit__(self, *exc):
                return False

        return Stream()


def listen(mic, vosk, seconds, monkeypatch=None):
    got = {"status": [], "level": [], "heard": []}
    lis = voice.VoiceListener("model", lambda a: None, got["status"].append,
                              on_level=got["level"].append, on_heard=got["heard"].append)
    if monkeypatch:
        monkeypatch.setitem(sys.modules, "sounddevice", mic)
        monkeypatch.setitem(sys.modules, "vosk", vosk)
        t = threading.Thread(target=lis.run, daemon=True)
    else:
        t = threading.Thread(target=lis._listen, args=(mic, vosk, object()), daemon=True)
    t.start()
    time.sleep(seconds)
    lis.stop()
    t.join(2)
    return lis, got


def test_a_silent_microphone_costs_nothing():
    """Ten seconds of silence: no decoding, one meter reading and one status, not ten a second."""
    vosk = FakeVosk()
    lis, got = listen(FakeMic([array("h", [0]) * BLOCK] * 100), vosk, 0.6)
    rec = lis._recognizer[1]
    assert rec.fed == [] and rec.finals == 0
    assert got["level"] == [0.0]
    assert got["status"] == ["Listening on Fake Mic"]


class Waits(threading.Event):
    """The listener's halt event, noting how long each wait between tries asked for."""

    def __init__(self):
        super().__init__()
        self.asked = []

    def wait(self, timeout=None):
        if timeout is not None:
            self.asked.append(timeout)
        return super().wait(timeout)


def test_a_missing_microphone_is_tried_less_and_less_often(monkeypatch):
    monkeypatch.setattr(voice, "RETRY_FIRST", 0.02)
    monkeypatch.setattr(voice, "RETRY_MOST", 0.16)
    mic, vosk = FakeMic(fail="Error querying device -1"), FakeVosk()
    monkeypatch.setitem(sys.modules, "sounddevice", mic)
    monkeypatch.setitem(sys.modules, "vosk", vosk)
    status = []
    lis = voice.VoiceListener("model", lambda a: None, status.append)
    lis._halt = waits = Waits()
    t = threading.Thread(target=lis.run, daemon=True)
    t.start()
    time.sleep(1.0)
    lis.stop()
    t.join(2)
    # The waits asked for, not the clock: a busy test machine can add 100 ms to any wait.
    assert len(waits.asked) >= 4 and len(mic.queried) in (len(waits.asked), len(waits.asked) + 1)
    assert waits.asked[:4] == pytest.approx([0.02, 0.04, 0.08, 0.16])
    assert waits.asked[4:] == pytest.approx([0.16] * len(waits.asked[4:]))
    assert status == ["Microphone problem: Error querying device -1. Retrying."]   # said once
    assert vosk.made == []   # no recognizer is built for a microphone that never opened


def test_a_microphone_that_stops_is_opened_again(monkeypatch):
    """A stream that stops sending (unplugged, or the device failed) used to leave voice
    "Listening" to nothing for good. Now it's opened again, with the same recognizer."""
    monkeypatch.setattr(voice, "RETRY_FIRST", 0.05)
    mic, vosk = FakeMic([tone(5000)] * 3, dies=True), FakeVosk()
    lis, got = listen(mic, vosk, 1.5, monkeypatch)
    assert mic.opened >= 2
    assert vosk.made == [RATE]
    assert "Microphone problem: the microphone stopped sending sound. Retrying." in got["status"]


# The app's windows ----------------------------------------------------------------

class Count(QObject):
    """Counts redraws and restyles in the given windows."""

    def __init__(self, *windows):
        super().__init__()
        self.windows = windows
        self.seen = []

    def eventFilter(self, obj, event):
        if (event.type() in (QEvent.Paint, QEvent.StyleChange) and isinstance(obj, QWidget)
                and obj.window() in self.windows):
            self.seen.append((type(obj).__name__, event.type().name))
        return False


def test_setup_sits_still_while_a_permission_stays_missing(qapp, tmp_path):
    """Zoom checks permissions every second while one is missing (no Accessibility on the
    proof's Mac). Setup used to restyle and redraw on every check, nothing having changed."""
    s = Settings(tmp_path / "s.json")
    s["speak"] = False
    b = PermBackend()
    app = ZoomApp(s, b, use_keys=False, use_voice=False, use_tray=False)
    app.start()
    QTest.qWait(600)   # the first run opens Setup
    w = app.setup_window
    assert w is not None and w.isVisible()
    count = Count(w, app.panel)
    qapp.installEventFilter(count)
    try:
        # Let Setup finish appearing first: on a Mac it repaints a few times after it shows.
        for _ in range(50):
            count.seen.clear()
            QTest.qWait(300)
            if not count.seen:
                break
        for _ in range(5):
            app._check_permissions()   # what the permission timer does each second
            QTest.qWait(40)
    finally:
        qapp.removeEventFilter(count)
    assert count.seen == []
    b.allowed = True
    app._check_permissions()
    assert w.perm_rows["accessibility"][0].text() == "✓"   # a change still shows at once
    w.close()


def test_nothing_ticks_on_after_every_action(qapp, tmp_path):
    """The conformance kit presses every action. Afterwards only Zoom's slow background
    checks may run: no dwell tick (30 ms), scanning or anything else left going."""
    app, b = make_app(tmp_path)
    app.start()
    hover(app.panel.buttons[1])      # someone resting the pointer on a panel button...
    app.panel.switch_pressed()       # ...and someone scanning with a switch
    for a in actions():
        ok, message = app.suite.invoke(a["id"], {}, "test")
        assert message
    assert not app.panel.isVisible()   # "panel" hid it
    QTest.qWait(1500)                  # messages disappear after 1.2 s
    timers = app.findChildren(QTimer) + [t for w in (app.panel, app.toast, app.badge)
                                         for t in w.findChildren(QTimer)]
    running = {t for t in timers if t.isActive()}
    assert running == {app.poll, app.perm_timer}, [(t.objectName(), t.interval()) for t in running]
    assert app.perm_timer.interval() >= 1000 and app.poll.interval() >= 400


def test_only_one_copy_runs(tmp_path):
    first = single_instance(tmp_path)
    assert first is not None and first.isLocked()
    assert single_instance(tmp_path) is None   # a second copy opening at the same moment steps aside
    first.unlock()
    assert single_instance(tmp_path) is not None


def test_a_lock_left_under_another_computer_name_is_taken_over(tmp_path):
    # Killed (power cut, force quit), then the Mac's name changed: Qt can't tell the owner is gone.
    (tmp_path / "running.lock").write_text("2147483000\nLimitless Zoom\nanother-name-for-this-mac\n")
    assert single_instance(tmp_path) is None
    taken = single_instance(tmp_path, take_over=True)
    assert taken is not None and taken.isLocked()
    taken.unlock()
