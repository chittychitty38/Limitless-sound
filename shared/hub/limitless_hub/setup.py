"""The guided setup: from how a musician plays, which apps open together and how they look.

The settings page asks two questions the first time it opens: how do you like to play,
and how should things look and sound. plan() turns the answers into the apps to open
with Limitless Sound and the shared settings every app follows. Nothing here is a
diagnosis: the musician picks what fits, and can change any of it afterwards.
"""

from __future__ import annotations

from . import catalog

# Each way of playing, in the order the page shows them, with the apps it brings in.
INPUTS: dict[str, tuple[str, str, list[str]]] = {
    "voice": ("My voice", "Say “record”, “solo track” or “zoom in”, in Logic Pro, Pro Tools or anywhere.",
              ["voice"]),
    "onehand": ("One hand on the keyboard", "The keys under one hand become play, record, undo and more.",
                ["onehand"]),
    "eyes": ("My eyes or my head", "Play notes and run the transport by looking at a webcam, and zoom the "
             "session by resting your gaze on big buttons.", ["gaze", "zoom"]),
    "switch": ("A switch or a foot pedal", "One button can reach every command, by scanning.",
               ["control", "zoom"]),
    "controller": ("An Xbox Adaptive Controller or a gamepad", "Every button becomes a command you choose.",
                   ["control"]),
    "color": ("I see colours differently", "The whole screen is recoloured so meters, tracks and plug-ins "
              "look right to you.", ["color"]),
    "vision": ("Bigger text and zoom", "Zoom the DAW by voice, one hand, dwell or a switch, with large "
               "text in every app.", ["zoom"]),
}
TEXT_SIZES = (1.0, 1.25, 1.5, 2.0)
BIG_TEXT = 1.5   # "Bigger text and zoom" never leaves text smaller than this


def plan(inputs: list, look: dict) -> dict:
    """The apps (in the suite's order) and shared settings for these answers."""
    chosen = [i for i in INPUTS if i in {str(x) for x in inputs or []}]
    wanted = {tool for i in chosen for tool in INPUTS[i][2]}
    tools = [t for t in catalog.TOOLS if t in wanted]
    look = look if isinstance(look, dict) else {}
    try:
        scale = float(look.get("textScale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    scale = min(max(scale, 1.0), 2.0)
    if "vision" in chosen:
        scale = max(scale, BIG_TEXT)
    prefs = {"textScale": scale}
    for key in ("highContrast", "reduceMotion", "speak"):
        if key in look:
            prefs[key] = bool(look[key])
    return {"inputs": chosen, "tools": tools, "prefs": prefs}


def choices() -> list[dict]:
    """What the page shows for the first question."""
    return [{"id": i, "label": label, "about": about} for i, (label, about, _) in INPUTS.items()]
