"""Limitless Zoom's words, in the suite's language.

English is written in the code, and SPANISH below maps it to Spanish, as on Limitless Sound's
own page. Text with no Spanish stays English. The language is the suite's (`language` in the
hub's shared settings) once the hub sends it, and the computer's own until then.

Words on screen are set with show(), or kept by the label that shows them (LiveText), so that
when the language changes show_again() puts each one in the new language, in place.
"""

import locale
import re
import subprocess
import sys
import weakref

# ---- which language (as the hub's limitless_hub/languages.py works it out) ---------------

LANGUAGES = ("en", "es")
DEFAULT = "en"


def tag(value):
    """'es', 'es-MX', 'es_ES.UTF-8' → 'es'; None when it isn't a language the suite has."""
    if not isinstance(value, str):
        return None
    primary = value.strip().replace("_", "-").split("-")[0].split(".")[0].lower()
    return primary if primary in LANGUAGES else None


def _mac_languages():
    out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                         text=True, timeout=5).stdout
    return [p.strip().strip('",') for p in out.splitlines() if p.strip().strip('",()')]


def _windows_languages():
    import ctypes
    lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    return [locale.windows_locale.get(lcid, "")]


def system_language(read=None):
    """The computer's first language that the suite has, or English."""
    try:
        if read is not None:
            found = read()
        elif sys.platform == "darwin":
            found = _mac_languages()
        elif sys.platform.startswith("win"):
            found = _windows_languages()
        else:
            found = [locale.getlocale()[0] or ""]
    except Exception:
        return DEFAULT
    for value in found:
        if tag(value):
            return tag(value)
    return DEFAULT


_computer = None   # the computer's language, looked up the first time it's needed
_suite = None      # the suite's language, once the hub sends it


def language():
    """The language Zoom shows: the suite's, else the computer's."""
    global _computer
    if _suite:
        return _suite
    if _computer is None:
        _computer = system_language()
    return _computer


def follow(value):
    """Use the language the hub sent. True when that changes the language. If the hub goes
    away, the last one it sent stays: the windows don't change language under the musician."""
    global _suite
    before = language()
    _suite = tag(value) or _suite
    return language() != before


# ---- words --------------------------------------------------------------------------

class Text(str):
    """Words in one language that remember their English, so again() can say them in another."""
    english = ""
    values = {}


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def t(text, /, **values):
    """The text in the language in use, with each {name} filled in from values."""
    out = SPANISH.get(text, text) if language() == "es" else text
    out = _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), out)
    said = Text(out)
    said.english, said.values = text, values
    return said


def again(text):
    """The same words in the language in use now. Text that didn't come from t() stays as it is."""
    if isinstance(text, Text):
        return t(text.english, **{k: again(v) for k, v in text.values.items()})
    return text


# ---- words on screen ----------------------------------------------------------------

_shown = {}   # (id of the widget, setter, its other arguments) -> (the widget, weakly; the words)


def keep(setter, text, *args):
    """Remember that setter(*args, text) put these words on screen, to put them again in another
    language. A widget's later words replace its earlier ones."""
    owner = setter.__self__
    _shown[(id(owner), setter.__name__, args)] = (weakref.ref(owner), text)


def show(setter, text, *args):
    """setter(*args, text), now and again each time the language changes."""
    keep(setter, text, *args)
    setter(*args, text)


def show_again():
    """Put every word on screen in the language in use now. Words that read the same in both
    are left alone, so a screen reader on them hears nothing new."""
    for (key, name, args), (ref, text) in list(_shown.items()):
        owner, now = ref(), again(text)
        if owner is None:
            del _shown[(key, name, args)]
        elif now != text:
            try:
                _shown[(key, name, args)] = (ref, now)
                getattr(owner, name)(*args, now)
            except RuntimeError:   # its window has closed for good
                del _shown[(key, name, args)]


# ---- Spanish ------------------------------------------------------------------------
# Neutral Spanish with tú, in the same words as Limitless Sound's page: "equipo" for computer,
# "Ajustes", "pulsador" for a switch, "barrido" for scanning, "permanencia" for dwell.
# macOS settings by the names Spanish macOS shows. Voice commands are in the language voice listens
# in (app.py's listening_language), which can differ from the windows', so a phrase to say is
# filled in ("Di «{phrase}» para probarlo"), never translated here.

SPANISH = {
    # What Zoom did: the big-text messages, and what it says out loud (actions.py, by its English)
    "Zoom in": "Acercar",
    "Zoom out": "Alejar",
    "Zoom in a lot": "Acercar mucho",
    "Zoom out a lot": "Alejar mucho",
    "Taller tracks": "Pistas más altas",
    "Shorter tracks": "Pistas más bajas",
    "Fit to window": "Ajustar a la ventana",
    "Bigger waveform": "Forma de onda más grande",
    "Smaller waveform": "Forma de onda más pequeña",
    "Magnifier on or off": "Activar o desactivar la lupa",
    "Magnify more": "Más aumento",
    "Magnify less": "Menos aumento",
    "Zoom preset 1": "Preajuste de zoom 1",
    "Zoom preset 2": "Preajuste de zoom 2",
    "Zoom preset 3": "Preajuste de zoom 3",
    "Zoom preset 4": "Preajuste de zoom 4",
    "Zoom preset 5": "Preajuste de zoom 5",
    "Again": "Otra vez",
    "Show or hide the zoom panel": "Mostrar u ocultar el panel de zoom",
    "Zoom keys on or off": "Activar o desactivar las teclas de zoom",
    "Voice paused": "Voz en pausa",
    "Voice listening": "Voz escuchando",
    "Zoom keys on": "Teclas de zoom activadas",
    "Zoom keys off": "Teclas de zoom desactivadas",
    "Zoom keys are ready": "Las teclas de zoom están listas",
    "Zoom key is {key}": "La tecla de zoom es {key}",
    "Switch is {key}": "El pulsador es {key}",
    "Ready. Say {phrase}, or tap {key}": "Todo listo. Di «{phrase}» o pulsa {key}",
    "{action} isn't available in {app}": "{action} no está disponible en {app}",
    "Unknown action {action}": "Acción desconocida: {action}",
    "Screen magnifier": "Lupa de pantalla",
    "Limitless Zoom has no action {action}.": "Limitless Zoom no tiene la acción {action}.",

    # The zoom keys badge and the panel
    "ZOOM KEYS ON": "TECLAS DE ZOOM ACTIVADAS",
    "What Zoom did": "Lo que hizo Zoom",
    "Zoom keys": "Teclas de zoom",
    "Limitless Zoom panel": "Panel de Limitless Zoom",
    "−  Zoom out": "−  Alejar",
    "+  Zoom in": "+  Acercar",
    "Fit": "Ajustar",
    "Magnifier": "Lupa",
    "−−  Out a lot": "−−  Alejar mucho",
    "++  In a lot": "++  Acercar mucho",
    "Scanning: off": "Barrido: no",   # short: two of these share a row of the panel
    "Scanning: on": "Barrido: sí",
    "Dwell: on": "Permanencia: sí",
    "Dwell: off": "Permanencia: no",
    "Zoom status": "Estado del zoom",
    "Zoom keys: off": "Teclas de zoom: desactivadas",
    "Zoom keys ON: E in, Q out, S taller, W shorter, A fit. Tap {key} to turn off.":
        "Teclas de zoom ACTIVADAS: E acercar, Q alejar, S más altas, W más bajas, A ajustar. "
        "Pulsa {key} para desactivarlas.",
    "Zoom keys off. Tap {key} to turn on.": "Teclas de zoom desactivadas. Pulsa {key} para activarlas.",
    "Voice commands": "Comandos de voz",
    "Voice: {status}": "Voz: {status}",
    "Voice: heard “{text}”": "Voz: oí «{text}»",
    "starting…": "iniciando…",
    "off": "desactivada",
    "Needs {names}. Open Setup from the menu bar.":
        "Necesita {names}. Abre «Configuración y ayuda» en la barra de menús.",
    "Zoom keys couldn't start: {problem}": "Las teclas de zoom no pudieron iniciarse: {problem}",
    "Couldn't press the zoom keys: {problem}": "No se pudieron pulsar las teclas de zoom: {problem}",
    "Couldn't change Open at login: {problem}": "No se pudo cambiar Abrir al iniciar sesión: {problem}",

    # Voice, and the language it listens in
    "downloading the voice model (about 40 MB), one time only…":
        "descargando el modelo de voz (unos 40 MB), solo esta vez…",
    "couldn't download the voice model: {problem}": "no se pudo descargar el modelo de voz: {problem}",
    "downloading the {language} voice model (about {size}), one time only…":
        "descargando el modelo de voz en {language} (unos {size}), solo esta vez…",
    "until the {language} voice model is downloaded ({size}, one time only), say the commands in English":
        "hasta que se descargue el modelo de voz en {language} ({size}, solo esta vez), di los comandos en inglés",
    "the {language} voice model couldn't be downloaded ({problem}), so say the commands in English":
        "no se pudo descargar el modelo de voz en {language} ({problem}), así que di los comandos en inglés",
    "couldn't download the {language} voice model: {problem}":
        "no se pudo descargar el modelo de voz en {language}: {problem}",
    "{status}; {note}": "{status}; {note}",
    "Voice commands in {language}": "Comandos de voz en {language}",
    "English": "inglés",
    "Spanish": "español",
    "Listening on {name}": "Escuchando en {name}",
    "Voice couldn't start: {problem}": "La voz no pudo iniciarse: {problem}",
    "Microphone problem: {problem}. Retrying.": "Problema con el micrófono: {problem}. Reintentando.",
    "{heard} (not sure, ignored)": "{heard} (sin certeza, se ignora)",

    # The menu bar menu
    "Show or hide zoom panel": "Mostrar u ocultar el panel de zoom",
    "Listen for voice commands": "Escuchar comandos de voz",
    "Speak each action": "Decir cada acción en voz alta",
    "Choose zoom keys on/off key…": "Elegir la tecla que activa las teclas de zoom…",
    "Choose switch key…": "Elegir la tecla del pulsador…",
    "Microphone": "Micrófono",
    "System default": "Predeterminado del sistema",
    "Voice command language": "Idioma de los comandos de voz",
    "Same as Limitless Sound ({language})": "Igual que Limitless Sound ({language})",
    "Open at login": "Abrir al iniciar sesión",
    "Setup and help…": "Configuración y ayuda…",
    "Quit Limitless Zoom": "Salir de Limitless Zoom",

    # Choosing a key
    "Zoom keys on/off": "Activar o desactivar las teclas de zoom",
    "Press the key you want to turn the zoom keys on and off.":
        "Pulsa la tecla con la que quieres activar y desactivar las teclas de zoom.",
    "Switch": "Pulsador",
    "Press your switch now.": "Presiona ahora tu pulsador.",
    "{prompt}\n\nYou can also tap Right Option, Right Command, Right Control or Right Shift on its own. "
    "Escape cancels.":
        "{prompt}\n\nTambién puedes pulsar sola la tecla Opción, Comando, Control o Mayúsculas de la derecha. "
        "Esc cancela.",
    "Cancel": "Cancelar",

    # Key names (keys.py)
    "not set": "sin asignar",
    "Escape": "Esc",
    "Scroll Lock": "Bloq Despl",
    "Pause": "Pausa",
    "Space": "Espacio",
    "Enter": "Intro",
    "Tab": "Tab",
    "Right Option": "Opción derecha",
    "Right Alt": "Alt derecha",
    "Right Control": "Control derecha",
    "Right Ctrl": "Ctrl derecha",
    "Right Command": "Comando derecha",
    "Right Windows key": "Windows derecha",
    "Right Shift": "Mayúsculas derecha",

    # Setup
    "Set up Limitless Zoom": "Configurar Limitless Zoom",
    "Limitless Zoom setup": "Configuración de Limitless Zoom",
    "Setup steps": "Pasos de la configuración",
    "Welcome to Limitless Zoom": "Te damos la bienvenida a Limitless Zoom",
    "Zoom Logic, Pro Tools, Ableton or your whole screen with your voice, one key, your eyes or a switch. "
    "This takes about a minute.":
        "Amplía Logic, Pro Tools, Ableton o toda la pantalla con la voz, una tecla, los ojos o un pulsador. "
        "Tarda un minuto más o menos.",
    "1. Allow access": "1. Permitir el acceso",
    "Permission": "Permiso",
    "{name}: {state}": "{name}: {state}",
    "allowed": "permitido",
    "not allowed yet": "todavía no permitido",
    "not known": "desconocido",
    "{name} (optional)": "{name} (opcional)",
    "Allow…": "Permitir…",
    "Allow {name}": "Permitir {name}",
    "Open Settings…": "Abrir Ajustes…",
    "Open Settings for {name}": "Abrir Ajustes para {name}",
    "2. Your zoom key": "2. Tu tecla de zoom",
    "Tap <b>{key}</b> to turn the zoom keys on. Then, with one hand: <b>E</b> zoom in, <b>Q</b> out, "
    "<b>S</b> taller, <b>W</b> shorter, <b>A</b> fit. Tap it again to turn them off. Try it now:":
        "Pulsa <b>{key}</b> para activar las teclas de zoom. Luego, con una mano: <b>E</b> acercar, "
        "<b>Q</b> alejar, <b>S</b> pistas más altas, <b>W</b> más bajas, <b>A</b> ajustar. Vuelve a pulsarla "
        "para desactivarlas. Pruébalo ahora:",
    "Zoom keys off. Tap {key}.": "Teclas de zoom desactivadas. Pulsa {key}.",
    "Use a different key…": "Usar otra tecla…",
    "3. Voice": "3. Voz",
    "Microphone:": "Micrófono:",
    "Microphone for voice commands": "Micrófono para los comandos de voz",
    "System default microphone": "Micrófono predeterminado del sistema",
    "Microphone level": "Nivel del micrófono",
    "What voice heard": "Lo que oyó la voz",
    "Say “{phrase}” to try it.": "Di «{phrase}» para probarlo.",
    "What you can say:": "Lo que puedes decir:",
    "<b>{action}</b>: {phrases}": "<b>{action}</b>: {phrases}",
    "“{phrase}”": "«{phrase}»",
    "Heard: “{text}”": "Oí: «{text}»",
    "Voice status": "Estado de la voz",
    "4. Switch (optional)": "4. Pulsador (opcional)",
    "If you use a switch, it starts the big-button panel scanning, then picks the lit button. "
    "Your switch key: <b>{key}</b>.":
        "Si usas un pulsador, inicia el barrido del panel de botones grandes y luego elige el botón iluminado. "
        "Tecla de tu pulsador: <b>{key}</b>.",
    "Set up my switch…": "Configurar mi pulsador…",
    "Open Limitless Zoom when I log in": "Abrir Limitless Zoom al iniciar sesión",
    "Start zooming": "Empezar",
    "Start (still needs {names})": "Empezar (aún falta {names})",
    "You can open this again any time from the magnifier icon in the menu bar.":
        "Puedes volver a abrir esto cuando quieras desde el icono de la lupa en la barra de menús.",

    # What macOS must allow (platforms.py, by its English)
    "Accessibility": "Accesibilidad",
    "Lets Limitless Zoom press zoom keys in Logic, Pro Tools and other apps.":
        "Permite que Limitless Zoom pulse las teclas de zoom en Logic, Pro Tools y otras apps.",
    "Input Monitoring": "Monitorización de entrada",
    "Lets your zoom key and switch work in every app.":
        "Permite que tu tecla de zoom y tu pulsador funcionen en todas las apps.",
    "For voice commands. Audio is understood on this Mac and never sent anywhere.":
        "Para los comandos de voz. El audio se entiende en este Mac y nunca se envía a ningún sitio.",
    "Screen zoom shortcuts": "Atajos de zoom de la pantalla",
    "In Accessibility > Zoom, turn on \"Use keyboard shortcuts to zoom\" so the whole screen can zoom "
    "outside your DAW.":
        "En Accesibilidad > Zoom, activa «Usar funciones rápidas de teclado para hacer zoom» para que toda "
        "la pantalla se pueda ampliar fuera de tu DAW.",
}
