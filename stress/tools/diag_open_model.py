"""Diag only (branch diag/vosk-model, never merged): a pytest plugin that gives Voice's open
recognizer a second model, VOSK_OPEN_MODEL, while its command recognizer keeps VOSK_MODEL.

The big English model (vosk-model-en-us-0.22) can't take a grammar at run time, so it could
only ever be Voice's open recognizer. This measures that pairing with the real-people tests:

    PYTHONPATH=stress/tools VOSK_OPEN_MODEL=/path/to/vosk-model-en-us-0.22 \\
      python -m pytest .../stress/test_voice_real_speech.py -p diag_open_model -s

The open model is loaded once and shared by every worker (Vosk models are read-only and
shared between recognizers); the command model stays one per worker, as the test has it.
Recognizers are built exactly as Listener._make_recognizers builds them, only from two models.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time

OPEN_MODEL = os.environ.get("VOSK_OPEN_MODEL")
_lock = threading.Lock()
_models = {}
_built = {"open": [], "commands": []}


def _shared(path):
    with _lock:
        if path not in _models:
            import vosk
            vosk.SetLogLevel(-1)
            started = time.perf_counter()
            _models[path] = vosk.Model(path)
            print(f"\n[diag] loaded {path} for the open recognizer in {time.perf_counter() - started:.1f} s, "
                  f"shared by every worker", flush=True)
        return _models[path]


def pytest_collection_finish(session):
    if not OPEN_MODEL:
        return
    import vosk
    from limitless_voice import audio

    def make(self, rate):
        model = self.load_model()
        open_model = _shared(OPEN_MODEL)
        started = time.perf_counter()
        recs = {"open": vosk.KaldiRecognizer(open_model, rate)}
        middle = time.perf_counter()
        if self.use_command_vocabulary:
            recs["commands"] = vosk.KaldiRecognizer(model, rate, json.dumps(audio.build_grammar(self.phrases)))
        _built["open"].append(middle - started)
        _built["commands"].append(time.perf_counter() - middle)
        return recs

    audio.Listener._make_recognizers = make
    print(f"\n[diag] Voice's open recognizer uses {OPEN_MODEL}; its command recognizer keeps "
          f"{os.environ.get('VOSK_MODEL')}", flush=True)


def pytest_terminal_summary(terminalreporter):
    for which, times in _built.items():
        if times:
            terminalreporter.write_line(
                f"[diag] built {len(times)} {which} recognizers in the tests: median "
                f"{statistics.median(times) * 1000:.0f} ms, {sum(times):.0f} s in all ({os.cpu_count()} workers at once)")
