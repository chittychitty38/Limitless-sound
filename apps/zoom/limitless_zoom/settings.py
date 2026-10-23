"""Settings, saved as JSON in the user's app-data folder so they survive updates."""

import copy
import json
import os
import sys
from pathlib import Path

from .actions import DEFAULT_LAYER_MAP

DEFAULTS = {
    "layer_key": None,         # one key turns the zoom keys on and off (None: per-OS default)
    "switch_key": "f19",       # the key an accessibility switch sends, for scanning
    "dwell_ms": 900,           # rest the pointer this long on a panel button to press it
    "scan_ms": 1500,           # how long each panel button stays lit while scanning
    "button_scale": 1.0,       # make panel buttons bigger or smaller
    "speak": True,             # say each action out loud
    "big_steps": 3,            # how many steps "zoom in a lot" takes
    "voice_enabled": True,
    "voice_device": None,      # microphone name, or None for the system default
    "voice_confidence": 0.55,  # 0-1, raise it if music triggers commands by mistake
    "voice_model": None,       # folder of a Vosk model, or None for the bundled one
    "voice_language": None,    # "en" or "es" for voice commands; None: the windows' language
    "show_panel_on_start": True,
    "first_run": True,
    "layer_map": DEFAULT_LAYER_MAP,
    "key_overrides": {},
}


def os_name():
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


def config_dir():
    name = os_name()
    if name == "mac":
        base = Path.home() / "Library" / "Application Support"
    elif name == "win":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Limitless Zoom"


def voice_app_models():
    """Where Limitless Voice keeps the speech models it downloads (its user data folder, as
    platformdirs names it), so a model Voice already has isn't downloaded again for Zoom."""
    name = os_name()
    if name == "mac":
        base = Path.home() / "Library" / "Application Support"
    elif name == "win":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "").strip() or Path.home() / ".local" / "share")
    return base / "Limitless Voice" / "models"


class Settings(dict):
    def __init__(self, path=None):
        super().__init__(copy.deepcopy(DEFAULTS))
        self.path = Path(path) if path else config_dir() / "settings.json"
        self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            for k, v in data.items():
                if k in DEFAULTS:
                    self[k] = v

    def get_layer_key(self):
        """Tap Right Option on a Mac (every Mac keyboard has one), Right Ctrl elsewhere."""
        return self["layer_key"] or ("right_alt" if os_name() == "mac" else "right_ctrl")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self, indent=2), encoding="utf-8")
        tmp.replace(self.path)
