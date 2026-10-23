"""Which keys each app uses for each zoom action, per operating system.

These are the factory key commands. Musicians who have remapped their DAW can
override any of them in settings.json under "key_overrides", for example:
    "key_overrides": {"protools": {"win": {"taller": "ctrl+alt+down"}}}
"""

# "match" strings are compared, case-insensitively, against the macOS bundle id
# or the Windows/Linux process name of the app in front.
TARGETS = {
    "logic": {
        "name": "Logic Pro",
        "match": ["com.apple.logic10"],
        "keys": {
            "mac": {"in": "cmd+right", "out": "cmd+left", "taller": "cmd+down",
                    "shorter": "cmd+up", "fit": "z"},
        },
    },
    # Logic Pro's keys. Apple's GarageBand guide only describes the zoom slider, so check these on
    # a real Mac (apps/voice/DAW-SHORTCUTS.md).
    "garageband": {
        "name": "GarageBand",
        "match": ["com.apple.garageband10"],
        "keys": {
            "mac": {"in": "cmd+right", "out": "cmd+left", "taller": "cmd+down",
                    "shorter": "cmd+up"},
        },
    },
    "protools": {
        "name": "Pro Tools",
        "match": ["com.avid.protools", "protools.exe", "protools"],
        "keys": {
            "mac": {"in": "cmd+]", "out": "cmd+[", "taller": "ctrl+down",
                    "shorter": "ctrl+up", "fit": "alt+a", "wave": "alt+cmd+]",
                    "waveOut": "alt+cmd+[", "preset1": "ctrl+1", "preset2": "ctrl+2",
                    "preset3": "ctrl+3", "preset4": "ctrl+4", "preset5": "ctrl+5"},
            # Pro Tools on Windows: Command -> Ctrl, Option -> Alt, Control -> Start.
            "win": {"in": "ctrl+]", "out": "ctrl+[", "taller": "win+down",
                    "shorter": "win+up", "fit": "alt+a", "wave": "ctrl+alt+]",
                    "waveOut": "ctrl+alt+[", "preset1": "win+1", "preset2": "win+2",
                    "preset3": "win+3", "preset4": "win+4", "preset5": "win+5"},
        },
    },
    "ableton": {
        "name": "Ableton Live",
        "match": ["com.ableton.live", "ableton live"],
        "keys": {
            "mac": {"in": "=", "out": "-", "fit": "z"},
            "win": {"in": "=", "out": "-", "fit": "z"},
        },
    },
    # REAPER's "zoom to project" (Cockos' Quick Start). Its guides disagree on which way + and -
    # zoom, so zoom in and out drive the screen magnifier until that's checked.
    "reaper": {
        "name": "REAPER",
        "match": ["com.cockos.reaper", "reaper.exe"],
        "keys": {
            "mac": {"fit": "cmd+pagedown"},
            "win": {"fit": "ctrl+pagedown"},
        },
    },
    # FL Studio's Playlist and Piano roll (Image-Line's manual): Page Up / Page Down zoom,
    # Shift+4 shows the whole song. FL64.exe, or "FL64 (scaled).exe", on Windows.
    "flstudio": {
        "name": "FL Studio",
        "match": ["com.image-line.flstudio", "fl64"],
        "keys": {
            "mac": {"in": "pageup", "out": "pagedown", "fit": "shift+4"},
            "win": {"in": "pageup", "out": "pagedown", "fit": "shift+4"},
        },
    },
    # The operating system's own screen magnifier. Used for magnifier actions
    # everywhere, and for zoom in/out in apps the tool doesn't know.
    "magnifier": {
        "name": "Screen magnifier",
        "match": [],
        "keys": {
            # Needs System Settings > Accessibility > Zoom > "Use keyboard shortcuts to zoom".
            "mac": {"magToggle": "alt+cmd+8", "magIn": "alt+cmd+=", "magOut": "alt+cmd+-"},
            # Windows Magnifier: Win+Plus starts and zooms, Win+Esc closes.
            "win": {"magOn": "win+=", "magOff": "win+esc", "magIn": "win+=",
                    "magOut": "win+-"},
            # GNOME zoom.
            "linux": {"magToggle": "win+alt+8", "magIn": "win+alt+=", "magOut": "win+alt+-"},
        },
    },
}


def find_target(app_id):
    """Return the target key for an app id, or 'magnifier' if it's not a known DAW."""
    if app_id:
        low = app_id.lower()
        for key, t in TARGETS.items():
            if any(m in low for m in t["match"]):
                return key
    return "magnifier"


def keys_for(target, os_name, overrides=None):
    keys = dict(TARGETS[target]["keys"].get(os_name, {}))
    if overrides:
        keys.update(overrides.get(target, {}).get(os_name, {}))
    return keys
