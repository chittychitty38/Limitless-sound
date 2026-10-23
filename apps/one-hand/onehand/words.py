"""One-Hand's words, in the suite's language.

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
    """The language One-Hand shows: the suite's, else the computer's."""
    global _computer
    if _suite:
        return _suite
    if _computer is None:
        _computer = system_language()
    return _computer


def follow(value):
    """Use the language the hub sent. True when that changes the language. If the hub goes
    away, the last one it sent stays: the window doesn't change language under the musician."""
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


def t(text, **values):
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
# "Ajustes", "pulsador" for a switch, "modo una mano". macOS settings by the names Spanish macOS
# shows. Key commands in One-Hand's layouts.json are here too, by their English label.

SPANISH = {
    # The window
    "One-Hand settings and key map": "Ajustes y mapa de teclas de One-Hand",
    "Keyboard access": "Acceso al teclado",
    "Set up keyboard access": "Configurar el acceso al teclado",
    "One-Hand can't use the keyboard yet, so your keys won't change.":
        "One-Hand aún no puede usar el teclado, así que tus teclas no cambian.",
    "One-hand mode is ON": "Modo una mano ACTIVADO",
    "One-hand mode is OFF": "Modo una mano DESACTIVADO",
    "Turns one-hand mode on or off. You can also double-tap Shift.":
        "Activa o desactiva el modo una mano. También puedes pulsar Mayúsculas dos veces.",
    "Click it, double-tap Shift, or press a foot pedal or switch set to F18.":
        "Haz clic en él, pulsa Mayúsculas dos veces o usa un pedal o un pulsador configurado como F18.",
    "One-hand mode status": "Estado del modo una mano",
    "Your keyboard works normally.": "Tu teclado funciona como siempre.",
    "{app} is in front: your {hand} keys are {app} commands.":
        "{app} está delante: las teclas de tu {hand} son comandos de {app}.",
    "Try it here: press the {hand} keys below to see what they do.":
        "Pruébalo aquí: pulsa las teclas de la {hand} que ves abajo para saber qué hacen.",
    "Waiting for Logic Pro or Pro Tools. Other apps type normally.":
        "Esperando a Logic Pro o Pro Tools. Las demás apps escriben con normalidad.",
    "left-hand": "mano izquierda",
    "right-hand": "mano derecha",
    "I'm using my": "Uso la",
    "Left hand": "Mano izquierda",
    "Right hand": "Mano derecha",
    "Use the left-hand layout": "Usar la distribución para la mano izquierda",
    "Use the right-hand layout": "Usar la distribución para la mano derecha",
    "Options": "Opciones",
    "Hold Space to type letters from the other side": "Mantén pulsado Espacio para escribir las letras del otro lado",
    "Double-tap Shift switches one-hand mode": "Pulsar Mayúsculas dos veces activa o desactiva el modo una mano",
    "Caps Lock switches one-hand mode": "Bloq Mayús activa o desactiva el modo una mano",
    "Show an ON badge at the top of the screen": "Mostrar el aviso ACTIVADO en la parte de arriba de la pantalla",
    "Play a sound when switching": "Reproducir un sonido al cambiar de modo",
    "Say “on” and “off” out loud": "Decir en voz alta «activado» y «desactivado»",
    "Larger text": "Texto más grande",
    "Keep this window on top": "Mantener esta ventana por encima de las demás",
    "Start with one-hand mode on": "Empezar con el modo una mano activado",
    "Open One-Hand when I log in": "Abrir One-Hand al iniciar sesión",
    "Your keys in": "Tus teclas en",
    "Show the key map for": "Mostrar el mapa de teclas de",
    "App whose keys are shown": "App cuyas teclas se muestran",
    "Key you just tried": "Tecla que acabas de probar",
    "{key} → {command}. In {app} that presses {keys}.": "{key} → {command}. En {app} pulsa {keys}.",
    "{key} key: {command}, presses {keys}": "Tecla {key}: {command}, pulsa {keys}",
    "{key} key: {command}": "Tecla {key}: {command}",
    "nothing": "nada",
    "Space still plays and stops. Holding ⌘, ⌥, ⌃ or ⇧ lets your normal shortcuts through. "
    "Other apps type normally.":
        "Espacio sigue reproduciendo y deteniendo. Si mantienes pulsada ⌘, ⌥, ⌃ o ⇧, tus atajos de siempre "
        "funcionan. Las demás apps escriben con normalidad.",
    "Keyboard control works on Mac and Windows. This computer can only show the window.":
        "El control del teclado funciona en Mac y Windows. Este equipo solo puede mostrar la ventana.",
    "This computer is not supported yet. The window works, but keys are not changed.":
        "Este equipo aún no es compatible. La ventana funciona, pero las teclas no cambian.",
    "Windows would not let the app watch the keyboard. Try restarting the app.":
        "Windows no ha permitido que la app lea el teclado. Prueba a reiniciar la app.",
    "Could not watch the keyboard (error {code}).": "No se pudo leer el teclado (error {code}).",

    # The ON badge, the menu bar menu, and what One-Hand says out loud
    "One-hand mode": "Modo una mano",
    "ONE-HAND ON  ·  {hand}  ·  {where}": "MODO UNA MANO ACTIVADO  ·  {hand}  ·  {where}",
    "waiting for your DAW": "esperando a tu DAW",
    "Turn one-hand mode on": "Activar el modo una mano",
    "Turn one-hand mode off": "Desactivar el modo una mano",
    "Show One-Hand window": "Mostrar la ventana de One-Hand",
    "Quit One-Hand": "Salir de One-Hand",
    "{name}: ON": "{name}: ACTIVADO",
    "{name}: off": "{name}: desactivado",
    "One-Hand is still running in the menu bar. Double-tap Shift any time to switch one-hand mode.":
        "One-Hand sigue funcionando en la barra de menús. Pulsa Mayúsculas dos veces cuando quieras para "
        "activar o desactivar el modo una mano.",
    "One hand on": "Modo una mano activado",
    "One hand off": "Modo una mano desactivado",

    # The first-launch page on a Mac
    "Welcome to Limitless One-Hand": "Te damos la bienvenida a Limitless One-Hand",
    "To turn your keys into Logic Pro and Pro Tools commands, macOS needs you to allow One-Hand to use the "
    "keyboard. This takes about a minute and you only do it once.":
        "Para convertir tus teclas en comandos de Logic Pro y Pro Tools, macOS necesita que permitas a One-Hand "
        "usar el teclado. Tarda un minuto más o menos y solo se hace una vez.",
    "Accessibility": "Accesibilidad",
    "Input Monitoring": "Monitorización de entrada",
    "It lets One-Hand press DAW shortcuts for you.": "Así One-Hand puede pulsar por ti los atajos del DAW.",
    "It lets One-Hand notice which keys you press.": "Así One-Hand puede saber qué teclas pulsas.",
    "Step {n}": "Paso {n}",
    "<b>Step {n}: {name}</b><br>Switch on <b>Limitless One-Hand</b>. {why}":
        "<b>Paso {n}: {name}</b><br>Activa <b>Limitless One-Hand</b>. {why}",
    "{name} not allowed yet": "{name}: todavía no permitido",
    "{name} allowed": "{name}: permitido",
    "Open {name} settings": "Abrir ajustes de {name}",
    "Open {name} settings in System Settings": "Abrir ajustes de {name} en Ajustes del Sistema",
    "If One-Hand isn't in the list, press <b>+</b> under the list and choose <b>Limitless One-Hand</b> from "
    "Applications. If macOS asks to quit and reopen the app, choose <b>Quit &amp; Reopen</b>.":
        "Si One-Hand no aparece en la lista, pulsa <b>+</b> debajo de la lista y elige <b>Limitless One-Hand</b> "
        "en Aplicaciones. Si macOS te pide salir y volver a abrir la app, elige <b>Salir y volver a abrir</b>.",
    "Setup status": "Estado de la configuración",
    "Waiting for you to switch these on. This page updates by itself.":
        "Esperando a que los actives. Esta página se actualiza sola.",
    "Both are on. macOS needs One-Hand to restart before it can use them.":
        "Los dos están activados. macOS necesita que One-Hand se reinicie para poder usarlos.",
    "Reopen One-Hand": "Volver a abrir One-Hand",
    "Look around first": "Echar un vistazo primero",
    "Skip for now and look at the key map": "Saltar por ahora y ver el mapa de teclas",
    "Open System Settings → Privacy & Security, then turn on Limitless One-Hand under both Accessibility "
    "and Input Monitoring.":
        "Abre Ajustes del Sistema → Privacidad y seguridad y activa Limitless One-Hand en Accesibilidad "
        "y en Monitorización de entrada.",
    "macOS has not given Limitless One-Hand permission to use the keyboard yet.":
        "macOS aún no ha dado permiso a Limitless One-Hand para usar el teclado.",

    # Answers to other apps in the suite
    "One-hand mode on": "Modo una mano activado",
    "One-hand mode off": "Modo una mano desactivado",
    "Left-hand layout": "Distribución para la mano izquierda",
    "Right-hand layout": "Distribución para la mano derecha",
    "{command} in {app}": "{command} en {app}",
    "No app One-Hand knows is in front.": "No hay delante ninguna app que One-Hand conozca.",
    "{app} has no {command} in the one-hand layout.": "{app} no tiene «{command}» en la distribución para una mano.",
    "This computer can't press keys.": "Este equipo no puede pulsar teclas.",
    "One-Hand has no action {action}.": "One-Hand no tiene la acción {action}.",

    # Key names (keys.py)
    "Space": "Espacio",
    "Return": "Intro",
    "Delete": "Eliminar",   # the key, and Pro Tools' command
    "Tab": "Tab",
    "Esc": "Esc",
    "Caps Lock": "Bloq Mayús",
    "Ctrl+": "Ctrl+",
    "Shift+": "Mayús+",
    "Alt+": "Alt+",
    "Win+": "Win+",

    # Key commands, by their label in layouts.json
    "Go to start": "Ir al principio",
    "Go to end": "Ir al final",
    "Back one bar": "Retroceder un compás",
    "Forward one bar": "Avanzar un compás",
    "Cycle on/off": "Activar/desactivar ciclo",
    "Loop playback": "Reproducción en bucle",
    "Metronome on/off": "Activar/desactivar metrónomo",
    "Undo": "Deshacer",
    "Redo": "Rehacer",
    "Record": "Grabar",
    "Save": "Guardar",
    "Split at playhead": "Dividir en el cursor de reproducción",
    "Separate clip": "Separar clip",
    "Heal separation": "Reparar separación",
    "New track": "Pista nueva",
    "New tracks": "Pistas nuevas",
    "Duplicate track": "Duplicar pista",
    "Duplicate": "Duplicar",
    "Mute track": "Silenciar pista",
    "Solo track": "Solo de pista",
    "Copy": "Copiar",
    "Cut": "Cortar",
    "Paste": "Pegar",
    "Zoom in": "Acercar",
    "Zoom out": "Alejar",
    "Zoom to fit": "Ajustar a la ventana",
    "Mixer": "Mezclador",
    "Editor": "Editor",
    "Library": "Biblioteca",
    "Edit/Mix window": "Ventana Edición/Mezcla",
}
