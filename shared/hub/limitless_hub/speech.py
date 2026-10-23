"""One voice for the whole suite.

When several tools confirm the same thing ("Record" from the controller and
"Record" from voice), the musician hears it once, and announcements wait their
turn instead of talking over each other. While it talks, the hub reports
`hub.speaking` so Limitless Voice can stop listening and never hears itself.
Text in another language is read by a voice for that language when the computer has one.
"""

from __future__ import annotations

import queue
import re
import shutil
import subprocess
import sys
import threading
import time

from . import languages

DUPLICATE_WINDOW = 1.5  # seconds: the same words twice in this time are said once
MAX_QUEUE = 3           # older announcements are dropped rather than read out late
RELIST_AFTER = 30.0     # seconds: a voice added in the computer's settings is found this soon
# Clearer voices first, where the computer has them; otherwise any voice for the language.
PREFERRED = {"es": ("Paulina", "Mónica", "Monica", "Juan", "Jorge")}
_LIST_WINDOWS = ("Add-Type -AssemblyName System.Speech; "
                 "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
                 "Where-Object Enabled | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }")


def _ps(text: str) -> str:
    return text.replace("'", "''")


def _command(text: str, lang: str = languages.DEFAULT, voice: str | None = None) -> list[str] | None:
    if sys.platform == "darwin":
        return ["say", "-v", voice, text] if voice else ["say", text]
    if sys.platform.startswith("win"):
        pick = f"$s.SelectVoice('{_ps(voice)}'); " if voice else ""
        return ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"{pick}$s.Speak('{_ps(text)}')"]
    other = lang != languages.DEFAULT
    for tool in ("spd-say", "espeak-ng", "espeak"):
        if shutil.which(tool):
            if tool == "spd-say":
                return [tool, *(["-l", lang] if other else []), "-w", text]
            return [tool, *(["-v", lang] if other else []), text]
    return None


def _list_voices() -> list[tuple[str, str]]:
    """(name, locale) of each voice the computer has, e.g. ("Paulina", "es_MX")."""
    if sys.platform == "darwin":
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
        found = (re.match(r"^(.*?)\s+([a-z]{2,3}[_-][A-Za-z0-9]+)\s+#", line) for line in out.splitlines())
        return [(m.group(1).strip(), m.group(2)) for m in found if m]
    if sys.platform.startswith("win"):
        out = subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", _LIST_WINDOWS],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return [tuple(line.strip().split("|", 1)) for line in out.splitlines() if "|" in line]
    return []


def voice_for(lang: str, voices: list[tuple[str, str]]) -> str | None:
    mine = [name for name, loc in voices if languages.tag(loc) == lang]
    for name in PREFERRED.get(lang, ()):
        if name in mine:
            return name
    return mine[0] if mine else None


class Speaker:
    def __init__(self, on_speaking=None, runner=None, clock=time.monotonic, list_voices=None):
        self.on_speaking = on_speaking or (lambda speaking: None)
        self.runner = runner or self._run
        self.clock = clock
        self.list_voices = list_voices or _list_voices
        self._voices: list[tuple[str, str]] | None = None
        self._listed_at = 0.0
        self._voice_lock = threading.Lock()
        self.recent: dict[str, float] = {}
        self.q: queue.Queue[tuple[str, str]] = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="speech")
        self.thread.start()

    def say(self, text: str, lang: str = languages.DEFAULT) -> bool:
        text = " ".join(text.split())[:300]
        if not text:
            return False
        now = self.clock()
        key = text.lower()
        if now - self.recent.get(key, -1e9) < DUPLICATE_WINDOW:
            return False
        self.recent = {k: t for k, t in self.recent.items() if now - t < DUPLICATE_WINDOW}
        self.recent[key] = now
        while self.q.qsize() >= MAX_QUEUE:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.q.put((text, lang))
        return True

    def voice(self, lang: str) -> str | None:
        """The voice to read this language with; None for the computer's own voice."""
        if lang == languages.DEFAULT:
            return None
        with self._voice_lock:
            stale = self.clock() - self._listed_at > RELIST_AFTER
            if self._voices is None or (stale and voice_for(lang, self._voices) is None):
                try:
                    self._voices = self.list_voices()
                except Exception:
                    self._voices = []
                self._listed_at = self.clock()
            return voice_for(lang, self._voices)

    def has_voice(self, lang: str) -> bool:
        """False when the computer has no voice for this language (Mac and Windows)."""
        if lang == languages.DEFAULT or not (sys.platform == "darwin" or sys.platform.startswith("win")):
            return True
        return self.voice(lang) is not None

    def _loop(self) -> None:
        while True:
            text, lang = self.q.get()
            self.on_speaking(True)
            try:
                self.runner(text, lang)
            except Exception:
                pass
            if self.q.empty():
                self.on_speaking(False)

    def _run(self, text: str, lang: str = languages.DEFAULT) -> None:
        cmd = _command(text, lang, self.voice(lang))
        if cmd:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, creationflags=flags)
