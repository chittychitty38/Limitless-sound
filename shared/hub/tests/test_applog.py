"""The app log every Limitless Sound app writes, and that each app's copy stays the same."""

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "shared" / "clients" / "python" / "applog.py"


def test_every_copy_matches_the_shared_one():
    for name in ("applog.py", "mac_keys.py"):
        shared = CANONICAL.parent / name
        copies = [p for p in ROOT.glob(f"**/{name}") if p != shared and "node_modules" not in p.parts
                  and ".claude" not in p.parts]
        assert copies, f"some app carries a copy of {name}"
        for p in copies:
            assert p.read_text() == shared.read_text(), f"{p.relative_to(ROOT)} differs from shared/clients/python/{name}"


def test_writes_errors_nothing_caught_including_in_threads(tmp_path):
    script = textwrap.dedent(f"""
        import sys, threading
        sys.path.insert(0, {str(CANONICAL.parent)!r})
        import applog
        print(applog.start("Test App", "1.2.3"))
        t = threading.Thread(target=lambda: 1 / 0, name="worker")
        t.start(); t.join()
        raise ValueError("nobody caught me")
    """)
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                       env={"LIMITLESS_SOUND_LOGS": str(tmp_path), "PATH": ""})
    assert r.returncode != 0
    log = (tmp_path / "Test App.log").read_text()
    assert "Started Test App 1.2.3" in log
    assert "Uncaught error in thread worker" in log and "ZeroDivisionError" in log
    assert "ValueError: nobody caught me" in log
    assert (tmp_path / "Test App crash.log").exists()


def test_a_folder_it_cannot_write_is_not_fatal(tmp_path, monkeypatch):
    sys.path.insert(0, str(CANONICAL.parent))
    import applog
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("LIMITLESS_SOUND_LOGS", str(blocker / "logs"))
    assert applog.start("Nowhere") is None
    logging.getLogger().handlers.clear()
