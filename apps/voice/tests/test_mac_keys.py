"""On a Mac with Apple silicon, pressing or listening for keys from another thread must
not stop the app (macOS traps text-input calls made off the main thread)."""
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


@unittest.skipIf(sys.platform != "darwin", "only Macs trap these calls")
class KeysFromAnyThread(unittest.TestCase):
    def test_keys_from_a_worker_thread_dont_crash(self):
        # In a child process: a failure here kills the whole process.
        code = textwrap.dedent("""
            import threading, time
            from limitless_voice import mac_keys
            assert mac_keys.prepare()
            from pynput import keyboard
            made = []
            t = threading.Thread(target=lambda: made.append(keyboard.Controller()))
            t.start(); t.join()
            hotkey = keyboard.GlobalHotKeys({"<ctrl>+<alt>+v": lambda: None})
            hotkey.start(); time.sleep(0.5); hotkey.stop()
            print("ok", len(made))
        """)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                           cwd=Path(__file__).resolve().parents[1])
        self.assertTrue(r.returncode == 0 and "ok 1" in r.stdout, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
