"""Where the app keeps its settings and layouts, and loading/saving them."""
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "Limitless One-Hand"


def config_dir():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def resource(name):
    """A file shipped inside the app (works both from source and when packaged)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "onehand" / name


def load_layouts():
    custom = config_dir() / "layouts.json"
    path = custom if custom.exists() else resource("layouts.json")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class Prefs:
    hand: str = "left"
    mirror_typing: bool = True
    double_shift: bool = True
    caps_lock_toggle: bool = False
    play_sounds: bool = True
    speak: bool = False
    keep_on_top: bool = False

    @classmethod
    def load(cls):
        try:
            data = json.loads((config_dir() / "settings.json").read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        try:
            config_dir().mkdir(parents=True, exist_ok=True)
            (config_dir() / "settings.json").write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass

    def toggle_keys(self):
        return ("f18", "caps_lock") if self.caps_lock_toggle else ("f18",)
