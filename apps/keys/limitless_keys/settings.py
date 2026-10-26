"""Settings, saved as JSON in the user's app-data folder so they survive updates."""

import copy
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "speak": True,             # say what each shortcut did
    "toasts": True,            # show it in big text
    "first_run": True,
    "enabled": True,
    "watch_logic_windows": True,   # plugin undo for Logic's own plugin windows
    # Names of buttons that only a Logic plugin window has, besides Undo and Redo.
    # Change these if your Logic is in another language.
    "logic_plugin_markers": ["Compare", "Bypass", "Link", "Copy", "Paste"],
}


def os_name():
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


def config_dir():
    override = os.environ.get("LIMITLESS_KEYS_HOME")
    if override:
        return Path(override)
    name = os_name()
    if name == "mac":
        base = Path.home() / "Library" / "Application Support"
    elif name == "win":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Limitless Keys"


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

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self, indent=2), encoding="utf-8")
        tmp.replace(self.path)
