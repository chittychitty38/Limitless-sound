"""One voice for the whole suite.

When several tools confirm the same thing ("Record" from the controller and
"Record" from voice), the musician hears it once, and announcements wait their
turn instead of talking over each other. While it talks, the hub reports
`hub.speaking` so Limitless Voice can stop listening and never hears itself.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import time

DUPLICATE_WINDOW = 1.5  # seconds: the same words twice in this time are said once
MAX_QUEUE = 3           # older announcements are dropped rather than read out late


def _command(text: str) -> list[str] | None:
    if sys.platform == "darwin":
        return ["say", text]
    if sys.platform.startswith("win"):
        safe = text.replace("'", "''")
        return ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                "Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"]
    for tool in ("spd-say", "espeak-ng", "espeak"):
        if shutil.which(tool):
            return [tool, "-w", text] if tool == "spd-say" else [tool, text]
    return None


class Speaker:
    def __init__(self, on_speaking=None, runner=None, clock=time.monotonic):
        self.on_speaking = on_speaking or (lambda speaking: None)
        self.runner = runner or self._run
        self.clock = clock
        self.recent: dict[str, float] = {}
        self.q: queue.Queue[str] = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="speech")
        self.thread.start()

    def say(self, text: str) -> bool:
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
        self.q.put(text)
        return True

    def _loop(self) -> None:
        while True:
            text = self.q.get()
            self.on_speaking(True)
            try:
                self.runner(text)
            except Exception:
                pass
            if self.q.empty():
                self.on_speaking(False)

    @staticmethod
    def _run(text: str) -> None:
        cmd = _command(text)
        if cmd:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, creationflags=flags)
