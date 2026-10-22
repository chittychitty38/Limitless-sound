"""The app log every Limitless Sound app writes, and that each app's copy stays the same."""

import logging
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "shared" / "clients" / "python" / "applog.py"
CANONICAL_JS = ROOT / "shared" / "clients" / "js" / "applog.js"
RUST = ROOT / "shared" / "clients" / "rust"
CANONICAL_RS = RUST / "src" / "applog.rs"


def _skipped(path: Path) -> bool:
    """Not the repository's own copy: hidden folders (other checkouts, virtual envs) and builds."""
    return any(part.startswith(".") or part in ("node_modules", "build", "dist", "target")
               for part in path.relative_to(ROOT).parts)


def test_every_copy_matches_the_shared_one():
    for canonical in (CANONICAL, CANONICAL.parent / "mac_keys.py", CANONICAL_JS, CANONICAL_RS):
        copies = [p for p in ROOT.glob(f"**/{canonical.name}") if p != canonical and not _skipped(p)]
        assert copies, f"some app carries a copy of {canonical.name}"
        for p in copies:
            assert p.read_text() == canonical.read_text(), \
                f"{p.relative_to(ROOT)} differs from {canonical.relative_to(ROOT).as_posix()}"


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


def test_crash_log_keeps_crashes_and_forgets_what_a_normal_run_survived(tmp_path):
    env = {**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path)}
    crash = tmp_path / "Test App crash.log"
    start = f"import sys, faulthandler; sys.path.insert(0, {str(CANONICAL.parent)!r}); import applog; applog.start('Test App')"
    # On Windows, faulthandler also reports exceptions that were handled (COM's 0x8001010d);
    # a run that then closes normally leaves none of it behind.
    subprocess.run([sys.executable, "-c", start + "; faulthandler.dump_traceback(applog._crash_file)"],
                   check=True, env=env)
    assert crash.read_text() == ""
    # A native crash ends the run before it can close, so where it was stays written down.
    r = subprocess.run([sys.executable, "-c", start + "; faulthandler._sigsegv()"], capture_output=True, env=env)
    assert r.returncode != 0
    text = crash.read_text()
    assert "fatal" in text.lower() and "<module>" in text, text


def test_a_folder_it_cannot_write_is_not_fatal(tmp_path, monkeypatch):
    sys.path.insert(0, str(CANONICAL.parent))
    import applog
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("LIMITLESS_SOUND_LOGS", str(blocker / "logs"))
    assert applog.start("Nowhere") is None
    logging.getLogger().handlers.clear()


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_log_writes_what_nothing_caught_and_still_crashes(tmp_path):
    script = textwrap.dedent(f"""
        const log = require({str(CANONICAL_JS)!r}).start('Test App', '1.2.3');
        log.info('ready'); log.warn('no MIDI ports'); log.error('model failed', new Error('bad model'));
        setTimeout(() => {{ throw new TypeError('nobody caught me'); }}, 10);
    """)
    r = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True,
                       env={**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path / "Logs")})
    assert r.returncode != 0, "the crash still happens; the log only watches"
    lines = (tmp_path / "Logs" / "Test App.log").read_text().splitlines()
    assert re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} INFO    Test App: Started Test App 1.2.3 on ", lines[0])
    assert lines[1].endswith("INFO    Test App: ready") and lines[2].endswith("WARNING Test App: no MIDI ports")
    assert lines[3].endswith("ERROR   Test App: model failed Error: bad model")
    log = "\n".join(lines)
    assert "CRITICAL Test App: Uncaught error TypeError: nobody caught me" in log


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_log_keeps_the_newest_megabyte_and_one_older_file(tmp_path):
    script = textwrap.dedent(f"""
        const applog = require({str(CANONICAL_JS)!r});
        const log = applog.start('Busy');
        for (let i = 0; i < 7000; i++) log.info('line ' + i + ' ' + 'x'.repeat(200));
    """)
    subprocess.run([shutil.which("node"), "-e", script], check=True,
                   env={**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path)})
    newest, older = tmp_path / "Busy.log", tmp_path / "Busy.log.1"
    assert newest.stat().st_size < 1024 * 1024 and 0 < older.stat().st_size < 1024 * 1024
    assert newest.read_text().splitlines()[-1].endswith("line 6999 " + "x" * 200)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Busy.log", "Busy.log.1"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_log_in_a_folder_it_cannot_write_is_not_fatal(tmp_path):
    (tmp_path / "file").write_text("not a folder")
    script = f"const log = require({str(CANONICAL_JS)!r}).start('Nowhere'); log.info('fine'); console.log(log.file)"
    r = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True, check=True,
                       env={**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path / "file" / "logs")})
    assert r.stdout.strip() == "null"


@pytest.fixture(scope="module")
def rust_applog():
    if not shutil.which("cargo"):
        pytest.skip("cargo not installed")
    build = subprocess.run(["cargo", "build", "-q", "--example", "applog_check"], cwd=RUST, capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    return RUST / "target" / "debug" / "examples" / ("applog_check.exe" if sys.platform == "win32" else "applog_check")


def test_rust_log_times_read_like_the_other_apps(rust_applog):
    # 1970, a leap day, a year end, today-ish, and the century's turn.
    for ms in (0, 951_782_400_000, 1_704_067_199_999, 1_761_132_553_123, 4_107_542_400_999):
        out = subprocess.run([str(rust_applog), "stamp", str(ms)], capture_output=True, text=True, check=True).stdout
        expected = f"{datetime.fromtimestamp(ms // 1000, timezone.utc):%Y-%m-%d %H:%M:%S},{ms % 1000:03d}"
        assert out.strip() == expected


def test_rust_log_writes_panics_and_the_app_still_panics(rust_applog, tmp_path):
    r = subprocess.run([str(rust_applog)], capture_output=True, text=True,
                       env={**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path / "Logs")})
    assert r.returncode != 0 and "nobody caught me" in r.stderr, "the usual panic still happens"
    lines = (tmp_path / "Logs" / "Test App.log").read_text().splitlines()
    assert re.match(r"\d{4}-\d\d-\d\d [\d:,]+ INFO    Test App: Started Test App 1\.2\.3 on .+, Rust, times in UTC$", lines[0])
    assert lines[1].endswith("INFO    Test App: ready") and lines[2].endswith("WARNING Test App: no shortcut")
    assert lines[3].endswith("ERROR   Test App: filter failed")
    log = "\n".join(lines)
    assert "CRITICAL Test App: Panic in thread worker: " in log and "worker gave up" in log
    assert "CRITICAL Test App: Panic in thread main: " in log


def test_rust_log_keeps_the_newest_megabyte_and_one_older_file(rust_applog, tmp_path):
    subprocess.run([str(rust_applog), "busy"], check=True, env={**os.environ, "LIMITLESS_SOUND_LOGS": str(tmp_path)})
    newest, older = tmp_path / "Busy.log", tmp_path / "Busy.log.1"
    assert newest.stat().st_size < 1024 * 1024 and 0 < older.stat().st_size < 1024 * 1024
    assert newest.read_text().splitlines()[-1].endswith("line 6999 " + "x" * 200)
