"""Limitless Keys and a real Limitless Undo plugin, talking over the link.

Needs the plugin's test program, built from plugin/ (see its CMakeLists.txt):
    LIMITLESS_UNDO_TEST_BINARY=/path/to/undo_plugin_tests pytest tests/test_plugin_link.py
Skipped without it.
"""

import os
import subprocess
import time

import pytest

from limitless_keys.plugin_undo import PluginUndo
from limitless_keys.runner import Context
from limitless_keys.undo_link import LinkServer

BINARY = os.environ.get("LIMITLESS_UNDO_TEST_BINARY")


@pytest.mark.skipif(not BINARY, reason="set LIMITLESS_UNDO_TEST_BINARY to the plugin's test program")
def test_option_command_z_undoes_a_change_in_the_real_plugin(tmp_path):
    pu = PluginUndo()
    server = LinkServer(tmp_path / "undo-link.json", pu.link_message, pu.link_closed, "test").start()
    pu.link = server
    env = dict(os.environ, LIMITLESS_SOUND_HOME=str(tmp_path))
    proc = subprocess.Popen([BINARY, "--link-demo"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        lines = []
        for want in ("linked", "changed"):
            while True:
                line = proc.stdout.readline().strip()
                assert line, f"plugin stopped early: {lines}"
                lines.append(line)
                if line == want:
                    break

        # The plugin told Keys about the change, with words for it.
        end = time.time() + 5
        while time.time() < end and pu.timeline.next_undo()[0] is None:
            time.sleep(0.02)
        src, step = pu.timeline.next_undo()
        assert src is not None and src.plugin == "Fake EQ"
        assert step.label == "Gain" and step.after.endswith("dB")

        # ⌥⌘Z, as Limitless Keys does it.
        ok, said = pu.undo(Context("com.avid.ProTools", 1))
        assert ok and said.startswith("Plugin undo: Gain back to") and said.endswith("Fake EQ")
        assert proc.stdout.readline().strip() == "restored"
        assert proc.wait(timeout=10) == 0
        # A plugin that's gone (track deleted, DAW quit) is forgotten.
        end = time.time() + 5
        while time.time() < end and src.key in pu.timeline.sources:
            time.sleep(0.02)
        assert src.key not in pu.timeline.sources
    finally:
        if proc.poll() is None:
            proc.kill()
        server.stop()
