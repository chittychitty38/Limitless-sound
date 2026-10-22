"""The JavaScript client (GazeStage) talking to Python tools through the real hub."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_server import Speaker, tool, wait_for  # noqa: F401 (fixtures)
from limitless_hub.server import Hub

JS = Path(__file__).resolve().parents[2] / "clients" / "js" / "check.js"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_client_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    hub = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    try:
        control, cseen = tool("control", [{"id": "record", "label": "Record", "intent": "daw.record"}, {"id": "ping", "label": "p"}])
        proc = subprocess.Popen(["node", str(JS), "3000"], stdout=subprocess.PIPE, text=True,
                                env={**__import__("os").environ})
        # A first Node start on a Windows runner can take several seconds (antivirus scan).
        assert wait_for(lambda: "gaze" in hub.bus.tools, 20)
        # eyes asked for Record; the controller pressed it
        assert wait_for(lambda: cseen["invokes"], 5)
        assert cseen["invokes"][0][0] == "record" and cseen["invokes"][0][2] == "gaze"
        assert wait_for(lambda: hub.bus.states.get("gaze.tracking") is True)
        # Python asks the JS app to play
        results = []
        control.invoke("daw.play", on_result=results.append)
        assert wait_for(lambda: results)
        assert results[0]["message"] == "js did play"
        control.did("ping")
        out, _ = proc.communicate(timeout=10)
        assert 'RESULT {"ok":true,"message":"did record"}' in out
        assert "EVENT control.ping" in out
        control.stop()
    finally:
        hub.stop()


RUST = Path(__file__).resolve().parents[2] / "clients" / "rust"


@pytest.mark.skipif(not shutil.which("cargo"), reason="cargo not installed")
def test_rust_client_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    build = subprocess.run(["cargo", "build", "-q", "--example", "check"], cwd=RUST, capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    hub = Hub({}, port=0, http_port=0, speaker=Speaker()).start()
    try:
        zoom, zseen = tool("zoom", [{"id": "in", "label": "Zoom in"}])
        exe = RUST / "target" / "debug" / "examples" / ("check.exe" if sys.platform == "win32" else "check")
        proc = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, text=True)
        assert wait_for(lambda: "color" in hub.bus.tools, 20)
        assert wait_for(lambda: hub.bus.states.get("color.ready") is True)  # sent on connect
        # Shared settings reach Rust on joining and on every change; it reports what it applied.
        assert wait_for(lambda: (hub.bus.states.get("color.prefs.applied") or {}).get("textScale") == 1.0)
        hub.bus.set_prefs({"textScale": 1.5})
        assert wait_for(lambda: (hub.bus.states.get("color.prefs.applied") or {}).get("textScale") == 1.5)
        assert wait_for(lambda: zseen["invokes"], 5)          # Rust asked Zoom to zoom in
        assert zseen["invokes"][0][2] == "color"
        results = []
        zoom.invoke("color.on", on_result=results.append)     # Python asks Rust to switch colors on
        assert wait_for(lambda: results)
        assert results[0]["message"] == "rust did on"
        assert wait_for(lambda: hub.bus.states.get("color.filter") is True)
        zoom.did("in")
        out, _ = proc.communicate(timeout=10)
        assert "CONNECTED true" in out and "EVENT zoom.in" in out
        zoom.stop()
    finally:
        hub.stop()
