"""Spoken feedback, so people who can't see the screen know what happened.

Mac uses the built-in `say` command; Windows uses SAPI through pyttsx3.
Messages are queued on one thread so they never block recognition, and a
new message cuts off a stale one.

While it talks, on_busy(True) is called so the app can stop listening:
otherwise the mic would hear our own voice and act on it.

Replies in another language are read by a system voice for it: on a Mac one of the
language's favourites (languages/<code>.yaml, voice) or any voice for it, on Windows a
voice whose name says the language. Without one, the computer's own voice reads them and
on_no_voice(language) is called once, so the app can say where to add a voice. System
settings are never changed from here.
"""

import queue
import re
import subprocess
import sys
import threading
import time


def mac_voices():
    """(name, locale) of each voice the Mac has, as `say -v ?` lists them: ("Paulina", "es_MX")."""
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10, check=False).stdout
    found = (re.match(r"^(.*?)\s+([a-z]{2,3}[_-][A-Za-z0-9]+)\s+#", line) for line in out.splitlines())
    return [(m.group(1).strip(), m.group(2)) for m in found if m]


def sapi_voices(tts):
    """(id, what it says about itself) of each voice pyttsx3 has. On Windows the names say the
    language: "Microsoft Sabina Desktop - Spanish (Mexico)"."""
    return [(v.id, f"{v.id} {v.name} {' '.join(map(str, v.languages or ()))}") for v in tts.getProperty("voices")]


def pick_voice(language, voices):
    """The voice to read a language with, from [(name, what it says about itself)]: one of the
    language's favourites, else any voice for the language. None for English (the computer's
    own voice, as always) or when there's none."""
    if language is None or language.is_english:
        return None
    words = [w.lower() for w in language.voice.get("match") or ()]
    code = re.compile(rf"(^|[^a-z]){re.escape(language.code)}[-_]")

    def speaks(desc):
        desc = desc.lower()
        return bool(code.search(desc)) or any(w in desc for w in words)

    mine = [name for name, desc in voices if speaks(desc)]
    for favourite in language.voice.get("mac") or ():
        for name in mine:
            if name == favourite or name.startswith(favourite + " ("):   # "Paulina (Enhanced)"
                return name
    return mine[0] if mine else None


class Speaker:
    def __init__(self, enabled=True, rate=190, on_busy=None, on_no_voice=None):
        self.enabled = enabled
        self.rate = rate
        self.on_busy = on_busy or (lambda busy: None)
        self.on_no_voice = on_no_voice or (lambda language: None)
        self.language = None   # what replies are in (a Language); None is English
        self._voices = {}      # language code -> the voice for it, or None if there's none
        self._q = queue.Queue()
        threading.Thread(target=self._run, name="speaker", daemon=True).start()

    def set_language(self, language):
        """Read replies in this language from now on. Its voice is looked for again, so one
        added since is found."""
        self.language = language
        if language is not None:
            self._voices.pop(language.code, None)

    def say(self, text):
        if not self.enabled or not text:
            return
        # drop anything not yet spoken: only the latest result matters
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._q.put(text)

    def _voice(self, listed):
        """The voice for the replies' language, looked for once; None for the computer's own."""
        lang = self.language
        if lang is None or lang.is_english:
            return None
        if lang.code not in self._voices:
            try:
                voices = listed()
            except Exception:  # noqa: BLE001  (no list: the computer's own voice reads it)
                voices = []
            self._voices[lang.code] = pick_voice(lang, voices)
            if self._voices[lang.code] is None:
                self.on_no_voice(lang)
        return self._voices[lang.code]

    def _run(self):
        engine = default = using = None
        while True:
            text = self._q.get()
            self.on_busy(True)
            try:
                if sys.platform == "darwin":
                    voice = self._voice(mac_voices)
                    proc = subprocess.Popen(["say", "-r", str(self.rate)] + (["-v", voice] if voice else []) + [text])
                    while proc.poll() is None:
                        if not self._q.empty():
                            proc.terminate()  # something newer to say
                            break
                        time.sleep(0.03)
                else:
                    if engine is None:
                        import pyttsx3
                        engine = pyttsx3.init()
                        default = using = engine.getProperty("voice")
                    voice = self._voice(lambda tts=engine: sapi_voices(tts)) or default
                    if voice != using:
                        engine.setProperty("voice", voice)
                        using = voice
                    engine.setProperty("rate", self.rate)
                    engine.say(text)
                    engine.runAndWait()
            except Exception:
                engine = None  # speech isn't essential; never crash for it
            finally:
                if self._q.empty():
                    time.sleep(0.25)  # let the room echo die down
                    self.on_busy(False)
