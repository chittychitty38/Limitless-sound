"""Start Limitless Control when the person logs in, quietly in the background."""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

LABEL = "org.limitlesssound.control"
RUN_VALUE = "Limitless Control"


def _command() -> list[str]:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if sys.platform == "darwin":
            # .../Limitless Control.app/Contents/MacOS/Limitless Control -> open the bundle,
            # so macOS treats it as the app the person gave permission to.
            bundle = exe.parents[2]
            if bundle.suffix == ".app":
                return ["/usr/bin/open", "-a", str(bundle), "--args", "--background"]
        return [str(exe), "--background"]
    return [sys.executable, "-m", "limitless_control", "--background"]


def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "limitless-control.desktop"


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_plist().exists()
    if sys.platform.startswith("win"):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, RUN_VALUE)
                return True
        except OSError:
            return False
    return _linux_desktop().exists()


def set_enabled(enabled: bool) -> None:
    cmd = _command()
    if sys.platform == "darwin":
        path = _mac_plist()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                plistlib.dump({"Label": LABEL, "ProgramArguments": cmd, "RunAtLoad": True}, f)
        elif path.exists():
            path.unlink()
    elif sys.platform.startswith("win"):
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except OSError:
                    pass
    else:
        path = _linux_desktop()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            exec_line = " ".join(f'"{c}"' if " " in c else c for c in cmd)
            path.write_text(f"[Desktop Entry]\nType=Application\nName=Limitless Control\nExec={exec_line}\n"
                            "X-GNOME-Autostart-enabled=true\n")
        elif path.exists():
            path.unlink()
