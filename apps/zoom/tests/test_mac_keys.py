"""On a Mac with Apple silicon, pressing or listening for keys from another thread must
not stop the app (macOS traps text-input calls made off the main thread)."""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="only Macs trap these calls")
def test_keys_from_a_worker_thread_dont_crash():
    # In a child process: a failure here kills the whole process.
    code = textwrap.dedent("""
        import threading, time
        from limitless_zoom import mac_keys
        assert mac_keys.prepare()
        from pynput import keyboard
        made = []
        t = threading.Thread(target=lambda: made.append(keyboard.Controller()))
        t.start(); t.join()
        listener = keyboard.Listener(on_press=lambda key: None)
        listener.start(); time.sleep(0.5); listener.stop()
        print("ok", len(made))
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                       cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 0 and "ok 1" in r.stdout, r.stdout + r.stderr
