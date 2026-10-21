"""Run what a command says to do on the current platform.

An action in a pack file is one of:
  keys: "cmd+s"          press a shortcut (or a list of them, in order)
  type: "some text"      type text
  open_app: "Logic Pro"  open or switch to an app
  menu: [Track, New…]    click a menu item (Mac only)
  applescript: "..."     run AppleScript (Mac only)
  shell: "..."           run a shell command
  wait: 0.3              pause, in seconds
  steps: [...]           several of the above in order
"""

from .platforms.base import NotSupported

# What people say -> the app's real name.
APP_ALIASES = {
    "logic": "Logic Pro", "logic pro": "Logic Pro", "logic pro x": "Logic Pro",
    "pro tools": "Pro Tools", "protools": "Pro Tools",
    "garageband": "GarageBand", "garage band": "GarageBand",
    "ableton": "Ableton Live", "ableton live": "Ableton Live", "live": "Ableton Live",
    "reaper": "REAPER", "studio one": "Studio One", "cubase": "Cubase",
    "fl studio": "FL Studio", "bitwig": "Bitwig Studio",
    "music": "Music", "finder": "Finder", "safari": "Safari",
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "file explorer": "File Explorer", "explorer": "File Explorer",
}


def _fill(value, params):
    if isinstance(value, str):
        # plain replace, not str.format: AppleScript uses braces for lists
        for name, v in params.items():
            value = value.replace("{" + name + "}", str(v))
        return value
    if isinstance(value, list):
        return [_fill(v, params) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, params) for k, v in value.items()}
    return value


def _q(s):
    """Quote a Python string as an AppleScript string literal."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def menu_script(path, process):
    """AppleScript that clicks a menu item by its titles, e.g. ["Track", "New Tracks…"]."""
    *parents, item = path
    ref = f"menu bar item {_q(parents[0])} of menu bar 1"
    for sub in parents[1:]:
        ref = f"menu item {_q(sub)} of menu 1 of {ref}"
    return (
        'tell application "System Events" to tell process ' + _q(process) + "\n"
        f"  click menu item {_q(item)} of menu 1 of {ref}\n"
        "end tell"
    )


def run_action(spec, params, platform, app_name=None):
    spec = _fill(spec, params)
    if "steps" in spec:
        for step in spec["steps"]:
            run_action(step, {}, platform, app_name)
        return
    if "keys" in spec:
        chords = spec["keys"] if isinstance(spec["keys"], list) else [spec["keys"]]
        for i, chord in enumerate(chords):
            if i:
                platform.wait(0.05)
            platform.press(chord, literal=bool(spec.get("literal")))
    elif "type" in spec:
        platform.type_text(spec["type"])
    elif "open_app" in spec:
        name = spec["open_app"].strip()
        platform.open_app(APP_ALIASES.get(name.lower(), name))
    elif "menu" in spec:
        platform.applescript(menu_script(spec["menu"], spec.get("process") or app_name or ""))
    elif "applescript" in spec:
        platform.applescript(spec["applescript"])
    elif "shell" in spec:
        platform.shell(spec["shell"])
    elif "wait" in spec:
        platform.wait(float(spec["wait"]))
    else:
        raise ValueError(f"action has nothing to do: {spec}")


__all__ = ["run_action", "NotSupported", "APP_ALIASES"]
