"""Spoken feedback, so people who can't see the screen know what happened.

Mac uses the built-in `say` command; Windows uses SAPI through pyttsx3.
Messages are queued on one thread so they never block recognition, and a
new message cuts off a stale one.

While it talks, on_busy(True) is called so the app can stop listening:
otherwise the mic would hear our own voice and act on it.
"""

import queue
import subprocess
import sys
import threading
import time


class Speaker:
    def __init__(self, enabled=True, rate=190, on_busy=None):
        self.enabled = enabled
        self.rate = rate
        self.on_busy = on_busy or (lambda busy: None)
        self._q = queue.Queue()
        threading.Thread(target=self._run, name="speaker", daemon=True).start()

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

    def _run(self):
        engine = None
        while True:
            text = self._q.get()
            self.on_busy(True)
            try:
                if sys.platform == "darwin":
                    proc = subprocess.Popen(["say", "-r", str(self.rate), text])
                    while proc.poll() is None:
                        if not self._q.empty():
                            proc.terminate()  # something newer to say
                            break
                        time.sleep(0.03)
                else:
                    if engine is None:
                        import pyttsx3
                        engine = pyttsx3.init()
                    engine.setProperty("rate", self.rate)
                    engine.say(text)
                    engine.runAndWait()
            except Exception:
                engine = None  # speech isn't essential; never crash for it
            finally:
                if self._q.empty():
                    time.sleep(0.25)  # let the room echo die down
                    self.on_busy(False)
