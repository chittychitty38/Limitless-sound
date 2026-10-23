"""Every zoom action the app knows, with the words shown and spoken for it,
and the phrases a musician can say to trigger it."""

# Actions sent to the DAW or the screen magnifier.
ZOOM_ACTIONS = {
    "in": "Zoom in",
    "out": "Zoom out",
    "bigIn": "Zoom in a lot",
    "bigOut": "Zoom out a lot",
    "taller": "Taller tracks",
    "shorter": "Shorter tracks",
    "fit": "Fit to window",
    "wave": "Bigger waveform",
    "waveOut": "Smaller waveform",
    "magToggle": "Magnifier on or off",
    "magIn": "Magnify more",
    "magOut": "Magnify less",
    "preset1": "Zoom preset 1",
    "preset2": "Zoom preset 2",
    "preset3": "Zoom preset 3",
    "preset4": "Zoom preset 4",
    "preset5": "Zoom preset 5",
}

# Actions the app handles itself.
APP_ACTIONS = {
    "again": "Again",
    "panel": "Show or hide the zoom panel",
    "keys": "Zoom keys on or off",
    "sleep": "Voice paused",
    "wake": "Voice listening",
}

LABELS = {**ZOOM_ACTIONS, **APP_ACTIONS}

# Spoken phrase -> action. Kept short and distinct so a small offline
# speech model can tell them apart through a cheap microphone.
VOICE_PHRASES = {
    "zoom in": "in",
    "closer": "in",
    "zoom out": "out",
    "zoom in more": "bigIn",
    "zoom way in": "bigIn",
    "zoom out more": "bigOut",
    "zoom way out": "bigOut",
    "taller": "taller",
    "taller tracks": "taller",
    "bigger tracks": "taller",
    "shorter": "shorter",
    "shorter tracks": "shorter",
    "smaller tracks": "shorter",
    "fit": "fit",
    "zoom to fit": "fit",
    "show everything": "fit",
    "bigger waveform": "wave",
    "smaller waveform": "waveOut",
    "magnifier": "magToggle",
    "magnifier on": "magToggle",
    "magnifier off": "magToggle",
    "magnify": "magIn",
    "magnify more": "magIn",
    "magnify less": "magOut",
    "preset one": "preset1",
    "preset two": "preset2",
    "preset three": "preset3",
    "preset four": "preset4",
    "preset five": "preset5",
    "again": "again",
    "do it again": "again",
    "show panel": "panel",
    "hide panel": "panel",
    "zoom keys": "keys",
    "stop listening": "sleep",
    "go to sleep": "sleep",
    "start listening": "wake",
    "wake up": "wake",
}

# The same in Spanish (voice.py's SPANISH listens for them). Where Limitless Voice has the
# action too, its words: "acercar" and "ampliar", "alejar" and "reducir", as Spanish menus and
# macOS's Zoom name them. Every word is one the Spanish speech model knows
# (stress/test_zoom_language.py checks), and the words people say alone were measured on real
# people (stress/README.md, "Zoom in Spanish").
SPANISH_PHRASES = {
    "acercar": "in",
    "ampliar": "in",
    "alejar": "out",
    "reducir": "out",
    "acercar mucho": "bigIn",
    "ampliar mucho": "bigIn",
    "alejar mucho": "bigOut",
    "reducir mucho": "bigOut",
    "más altas": "taller",
    "pistas más altas": "taller",
    "más bajas": "shorter",
    "pistas más bajas": "shorter",
    "ajustar": "fit",
    "ajustar a la ventana": "fit",
    "mostrar todo": "fit",
    "ver todo": "fit",
    "onda más grande": "wave",
    "forma de onda más grande": "wave",
    "onda más pequeña": "waveOut",
    "forma de onda más pequeña": "waveOut",
    "lupa": "magToggle",
    "activar la lupa": "magToggle",
    "desactivar la lupa": "magToggle",
    "aumentar": "magIn",
    "más aumento": "magIn",
    "disminuir": "magOut",
    "menos aumento": "magOut",
    "preajuste uno": "preset1",
    "preajuste dos": "preset2",
    "preajuste tres": "preset3",
    "preajuste cuatro": "preset4",
    "preajuste cinco": "preset5",
    "otra vez": "again",
    "repite": "again",
    "mostrar el panel": "panel",
    "ocultar el panel": "panel",
    "mostrar panel": "panel",
    "ocultar panel": "panel",
    "teclas de zoom": "keys",
    "deja de escuchar": "sleep",
    "a dormir": "sleep",
    "empieza a escuchar": "wake",
    "despierta": "wake",
}

# One-handed zoom layer: key -> action. All under the left hand.
DEFAULT_LAYER_MAP = {
    "e": "in", "q": "out", "s": "taller", "w": "shorter", "a": "fit",
    "r": "bigIn", "f": "bigOut", "z": "magToggle", "x": "magIn", "c": "magOut",
    "1": "preset1", "2": "preset2", "3": "preset3", "4": "preset4", "5": "preset5",
}

# Buttons on the big-button panel, in scanning order.
PANEL_BUTTONS = [
    ("out", "−  Zoom out"), ("in", "+  Zoom in"),
    ("shorter", "Shorter tracks"), ("taller", "Taller tracks"),
    ("fit", "Fit"), ("magToggle", "Magnifier"),
    ("bigOut", "−−  Out a lot"), ("bigIn", "++  In a lot"),
]
