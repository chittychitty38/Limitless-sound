import subprocess
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="reads macOS preferences")


def test_setup_sees_a_setting_change_made_by_another_app():
    """Setup checks the screen-zoom shortcut every second; it must see System Settings change it."""
    from limitless_zoom.platforms import MacBackend

    domain = f"org.limitlesssound.zoom.test-{uuid.uuid4().hex[:8]}"
    try:
        assert MacBackend.read_pref(domain, "hotkeys") is None
        for value in (True, False, True):
            subprocess.run(["defaults", "write", domain, "hotkeys", "-bool", "true" if value else "false"], check=True)
            assert bool(MacBackend.read_pref(domain, "hotkeys")) is value
    finally:
        subprocess.run(["defaults", "delete", domain], capture_output=True)


def test_zoom_shortcut_state_matches_defaults():
    from limitless_zoom.platforms import MacBackend

    out = subprocess.run(["defaults", "read", "com.apple.universalaccess", "closeViewHotkeysEnabled"],
                         capture_output=True, text=True).stdout.strip()
    expected = {"1": "ok", "0": "missing"}.get(out, "unknown")
    assert MacBackend._zoom_shortcuts(MacBackend.__new__(MacBackend)) == expected
