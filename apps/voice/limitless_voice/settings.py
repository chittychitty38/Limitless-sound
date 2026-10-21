"""User settings, saved as JSON in the normal per-user config folder."""

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "Limitless Voice"


def config_dir():
    return Path(user_config_dir(APP_NAME, appauthor=False))


def data_dir():
    return Path(user_data_dir(APP_NAME, appauthor=False))


def user_packs_dir():
    """Where people put their own command packs. Created on first run."""
    return data_dir() / "My Commands"


@dataclass
class Settings:
    mic_name: str = ""             # empty = system default
    model: str = ""                # empty = default model
    speak_feedback: bool = True    # say what happened out loud
    voice_rate: int = 190          # words per minute for spoken feedback
    start_listening: bool = True   # awake at launch (else asleep until "wake up")
    command_vocabulary: bool = True
    keep_on_top: bool = False
    text_scale: float = 1.0
    high_contrast: bool = False
    hotkey: str = ""               # e.g. "<ctrl>+<alt>+l"; toggles listening
    first_run_done: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls):
        path = config_dir() / "settings.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self):
        path = config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
