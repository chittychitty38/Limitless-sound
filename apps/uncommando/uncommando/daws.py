"""The DAWs Uncommando knows by name, and a few of their factory shortcuts.

"match" strings are compared, case-insensitively, against the macOS bundle id
of the app in front, or the host name an Uncommando plugin reports.
"""

DAWS = {
    "logic": {
        "name": "Logic Pro",
        "match": ["com.apple.logic10", "com.apple.logic", "logic pro", "apple logic"],
        # Logic keeps its own undo for each plugin window (the Undo and Redo
        # buttons at the top of it), so plugin undo works there with no plugin.
        "plugin_windows": True,
        "factory": {
            "cmd+z": "Undo",
            "shift+cmd+z": "Redo",
            "alt+cmd+z": "Undo History (in some Logic versions)",
            "alt+z": "Undo History (in some Logic versions)",
        },
    },
    "garageband": {
        "name": "GarageBand",
        "match": ["com.apple.garageband10", "com.apple.garageband", "garageband"],
        "factory": {"cmd+z": "Undo", "shift+cmd+z": "Redo"},
    },
    "protools": {
        "name": "Pro Tools",
        "match": ["com.avid.protools", "pro tools", "protools"],
        "factory": {
            "cmd+z": "Undo",
            "shift+cmd+z": "Redo",
            "alt+cmd+z": "Restore Last Selection",
        },
    },
    "ableton": {
        "name": "Ableton Live",
        "match": ["com.ableton.live", "ableton live", "ableton"],
        "factory": {"cmd+z": "Undo", "shift+cmd+z": "Redo"},
    },
    "cubase": {
        "name": "Cubase / Nuendo",
        "match": ["com.steinberg.cubase", "com.steinberg.nuendo", "cubase", "nuendo"],
        "factory": {"cmd+z": "Undo", "shift+cmd+z": "Redo"},
    },
    "studioone": {
        "name": "Studio One",
        "match": ["com.presonus.studioone", "studio one", "studioone"],
        "factory": {"cmd+z": "Undo", "cmd+y": "Redo"},
    },
    "reaper": {
        "name": "REAPER",
        "match": ["com.cockos.reaper", "reaper"],
        "factory": {"cmd+z": "Undo", "shift+cmd+z": "Redo"},
    },
    "bitwig": {
        "name": "Bitwig Studio",
        "match": ["com.bitwig", "bitwig"],
        "factory": {"cmd+z": "Undo", "shift+cmd+z": "Redo"},
    },
    "flstudio": {
        "name": "FL Studio",
        "match": ["com.image-line.flstudio", "fl studio", "fl64"],
        "factory": {"cmd+z": "Undo"},
    },
    "dp": {
        "name": "Digital Performer",
        "match": ["com.motu.digitalperformer", "digital performer"],
        "factory": {"cmd+z": "Undo"},
    },
    "reason": {
        "name": "Reason",
        "match": ["com.propellerheads.reason", "com.reasonstudios.reason", "reason"],
        "factory": {"cmd+z": "Undo"},
    },
}

# Profiles that aren't one app.
DAWS_SCOPE = "daws"       # every DAW above
ALL_SCOPE = "*"           # every app at all
SCOPE_NAMES = {DAWS_SCOPE: "Every DAW", ALL_SCOPE: "Every app"}


def find_daw(app_id):
    """The DAWS key for a bundle id or host name, or None if it isn't a DAW."""
    if not app_id:
        return None
    low = str(app_id).lower()
    for key, daw in DAWS.items():
        if any(m in low for m in daw["match"]):
            return key
    return None


def scope_name(scope):
    if scope in SCOPE_NAMES:
        return SCOPE_NAMES[scope]
    if scope in DAWS:
        return DAWS[scope]["name"]
    return scope


def factory_use(scope, combo_text):
    """What a DAW's own key command for this shortcut does, if we know it."""
    daws = DAWS.values() if scope in (DAWS_SCOPE, ALL_SCOPE) else [DAWS.get(scope, {})]
    found = {}
    for d in daws:
        what = d.get("factory", {}).get(combo_text)
        if what:
            found.setdefault(what, []).append(d["name"])
    return found
