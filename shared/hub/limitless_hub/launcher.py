"""Finding, opening and starting the suite's tools, and starting the hub at sign-in."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import catalog

LAUNCH_AGENT_ID = "org.limitlesssound.hub"


def _detached_kwargs() -> dict:
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}


def open_in_browser(url: str) -> None:
    """Open a page without waiting for the browser. Python's webbrowser waits for
    osascript on a Mac, which can take half a minute; the hub has to answer within 3 s."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()


def _app_bundle(exe: Path) -> Path | None:
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


class Launcher:
    def __init__(self, settings: dict, settings_url=lambda: "", popen=subprocess.Popen, run=subprocess.run):
        self.settings = settings
        self.settings_url = settings_url
        self.popen = popen
        self.run = run

    def find(self, tool: str) -> Path | None:
        if tool not in catalog.TOOLS:
            return None
        return catalog.find_install(tool, self.settings.get("installPaths"))

    def open(self, tool: str) -> dict:
        exe = self.find(tool)
        spec = catalog.TOOLS[tool]
        if exe is None:
            return {"ok": False, "message": f"{spec['name']} isn't installed on this computer."}
        args = spec.get("launch_args", [])
        try:
            bundle = _app_bundle(exe) if sys.platform == "darwin" else None
            if bundle is not None:
                cmd = ["open", "-g", str(bundle)] + (["--args", *args] if args else [])
            else:
                cmd = [str(exe), *args]
            self.popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_detached_kwargs())
        except OSError as e:
            return {"ok": False, "message": f"Couldn't open {spec['name']}: {e}"}
        return {"ok": True, "message": f"Opening {spec['name']}"}

    def open_many(self, tools: list[str]) -> dict:
        opened = [catalog.TOOLS[t]["name"] for t in tools if t in catalog.TOOLS and self.open(t)["ok"]]
        if not opened:
            return {"ok": False, "message": "None of the chosen tools are installed."}
        return {"ok": True, "message": "Opening " + ", ".join(opened)}

    def run_cli(self, tool: str, action: str, args: dict) -> tuple[bool, str]:
        exe = self.find(tool)
        if exe is None:
            return False, ""
        cmd = catalog.cli_command(tool, action, args, exe)
        if cmd is None:
            return False, f"Open {catalog.TOOLS[tool]['name']} so it can do that."
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = self.run(cmd, capture_output=True, text=True, timeout=10, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        out = (r.stdout or "").strip().splitlines()
        return r.returncode == 0, out[-1] if out else ""

    def open_settings(self) -> dict:
        url = self.settings_url()
        if url:
            open_in_browser(url)
        return {"ok": True, "message": "Opening Limitless Sound settings"}


# ------------------------------------------------------------------ start at sign-in

def hub_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    return [sys.executable, "-m", "limitless_hub", "--background"]


def _mac_agent() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "limitless-sound-hub.desktop"


def autostart_enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_agent().exists()
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "Limitless Sound")
            return True
        except OSError:
            return False
    return _linux_desktop().exists()


def set_autostart(on: bool) -> None:
    cmd = hub_command()
    if sys.platform == "darwin":
        path = _mac_agent()
        if not on:
            path.unlink(missing_ok=True)
            return
        exe = cmd[0]
        bundle = _app_bundle(Path(exe))
        args = ["/usr/bin/open", "-g", str(bundle), "--args", "--background"] if bundle else cmd
        items = "".join(f"<string>{a}</string>" for a in args)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0"><dict><key>Label</key><string>{LAUNCH_AGENT_ID}</string>'
            f'<key>ProgramArguments</key><array>{items}</array>'
            '<key>RunAtLoad</key><true/></dict></plist>\n')
        return
    if sys.platform.startswith("win"):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Limitless Sound", 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, "Limitless Sound")
                except OSError:
                    pass
        return
    path = _linux_desktop()
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Desktop Entry]\nType=Application\nName=Limitless Sound\n"
                    f"Exec={subprocess.list2cmdline(cmd)}\nX-GNOME-Autostart-enabled=true\n")
