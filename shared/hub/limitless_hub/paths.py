"""Where the suite keeps its shared files, the same on every tool.

Every Limitless Sound tool finds the hub through `link.json` in this folder:
  Mac      ~/Library/Application Support/Limitless Sound/
  Windows  %APPDATA%\\Limitless Sound\\
  Linux    ~/.config/Limitless Sound/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SUITE_NAME = "Limitless Sound"
DEFAULT_PORT = 47900       # tools connect here (one JSON message per line)
DEFAULT_HTTP_PORT = 47901  # settings page and one-shot triggers


def config_dir() -> Path:
    override = os.environ.get("LIMITLESS_SOUND_HOME")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / SUITE_NAME
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / SUITE_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / SUITE_NAME


def link_file() -> Path:
    return config_dir() / "link.json"


def settings_file() -> Path:
    return config_dir() / "hub.json"


def write_private(path: Path, data: dict) -> None:
    """Write JSON readable only by this user (the file holds the hub's token)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
