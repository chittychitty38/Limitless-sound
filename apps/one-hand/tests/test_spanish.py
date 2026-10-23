"""One-Hand in the suite's language: every word has Spanish, the windows show it, and they
change in place when the musician picks another language in Limitless Sound."""
import ast
import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no windows pop up while testing

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox, QLabel,  # noqa: E402
                               QSystemTrayIcon, QWidget)

from onehand import keys, limitless_link, platform_sim, words  # noqa: E402
from onehand.app import MainWindow  # noqa: E402
from onehand.platform_sim import SimBackend  # noqa: E402
from onehand.settings import APP_NAME, Prefs, load_layouts  # noqa: E402
from onehand.words import SPANISH, t  # noqa: E402

PACKAGE = Path(words.__file__).parent
PLACEHOLDER = re.compile(r"\{(\w+)\}")
LETTERS = re.compile(r"[^\W\d_]{2}")


# ---- the words ---------------------------------------------------------------------------

def calls_to_t():
    """Every t("…") in One-Hand: where, the English, and the names it fills in (None if it can't tell)."""
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names = None if any(k.arg is None for k in node.keywords) else {k.arg for k in node.keywords}
                yield f"{path.name}:{node.lineno}", node.args[0].value, names


def test_every_word_in_the_code_has_spanish():
    found = list(calls_to_t())
    assert len(found) > 80
    missing = [f"{where} {en!r}" for where, en, _ in found if en not in SPANISH]
    assert not missing, "no Spanish for:\n" + "\n".join(missing)
    unfilled = [f"{where} {en!r}" for where, en, names in found
                if names is not None and names != set(PLACEHOLDER.findall(en))]
    assert not unfilled, "placeholders not filled in:\n" + "\n".join(unfilled)


def test_layouts_and_key_names_have_spanish():
    # Not written as t("…") in the code: the key commands in layouts.json, by their English label,
    # the key names, and what the stand-in backend says.
    layouts = json.loads((PACKAGE / "layouts.json").read_text(encoding="utf-8"))
    used = {c[part] for a in layouts["apps"] for c in a["commands"] for part in ("label", "note") if c.get(part)}
    used |= {name for name in keys.KEY_CAPS.values() if LETTERS.search(name)}
    used |= {name for caps in keys.MOD_CAPS.values() for name in caps.values() if LETTERS.search(name)}
    used.add(platform_sim.UNSUPPORTED)
    assert not sorted(used - SPANISH.keys()), sorted(used - SPANISH.keys())


def test_spanish_keeps_every_placeholder_and_tag():
    for en, es in SPANISH.items():
        assert sorted(PLACEHOLDER.findall(en)) == sorted(PLACEHOLDER.findall(es)), en
        assert sorted(re.findall(r"<[^>]+>", en)) == sorted(re.findall(r"<[^>]+>", es)), en


# Calls that put words on screen, or say them out loud.
SHOWN_BY = {"setText", "setAccessibleName", "setAccessibleDescription", "setToolTip", "setWindowTitle",
            "setTitle", "showMessage", "addAction", "addMenu", "addItem", "show_text", "say", "speak",
            "announce", "label", "LiveText", "QLabel", "QPushButton", "QCheckBox", "QAction"}


def test_no_english_reaches_the_screen_without_t():
    raw = []
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in SHOWN_BY:
                for arg in node.args:
                    words_in = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else \
                        "".join(v.value for v in arg.values if isinstance(v, ast.Constant)) \
                        if isinstance(arg, ast.JoinedStr) else ""
                    if LETTERS.search(words_in):
                        raw.append(f"{path.name}:{node.lineno} {ast.unparse(arg)[:70]}")
    assert not raw, "words shown without t():\n" + "\n".join(raw)


def test_t_fills_in_and_says_it_again_in_another_language(monkeypatch):
    said = t("{key} key: {command}", key="E", command=t("Record"))
    assert said == "E key: Record"
    assert t("{text}, {values}", text="any name", values="works") == "any name, works"
    monkeypatch.setattr(words, "_suite", "es")
    assert t("Record") == "Grabar" and words.again(said) == "Tecla E: Grabar"
    assert t("Not in the table") == "Not in the table"   # no Spanish: it stays English
    assert words.again("plain text") == "plain text"


def test_the_language_is_the_suites_else_the_computers(monkeypatch):
    assert words.tag("es-MX") == "es" and words.tag("es_ES.UTF-8") == "es" and words.tag("fr") is None
    assert words.system_language(lambda: ["fr-FR", "es-ES"]) == "es"
    assert words.system_language(lambda: ["de-DE"]) == "en"

    def broken():
        raise OSError("no defaults")

    assert words.system_language(broken) == "en"
    monkeypatch.setattr(words, "_computer", "es")
    assert words.language() == "es"                          # no hub yet: the computer's
    assert words.follow("en") and words.language() == "en"   # the hub's, once it says
    assert not words.follow("en") and not words.follow("klingon") and not words.follow(None)
    assert words.language() == "en"


# ---- the windows -------------------------------------------------------------------------

@pytest.fixture
def make(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))         # no hub here...
    monkeypatch.setattr(limitless_link, "launch_hub", lambda: False)  # ...and don't open one
    monkeypatch.setattr(Prefs, "save", lambda self: None)              # leave the real settings alone
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))   # the menu too
    QApplication.instance() or QApplication([])
    made = []

    def make(**backend):
        w = MainWindow(SimBackend(front_app="limitless.sim", **backend), Prefs(), load_layouts())
        w.sent = []
        w.suite.link.state = lambda key, value: w.sent.append((key, value))
        made.append(w)
        return w

    yield make
    for w in made:
        w.shutdown()
        w.hide()


def busy(w):
    """One-hand mode on, a key just tried: the most words the main page shows."""
    w.engine.set_enabled(True)
    w.tick()
    w.show_practice("e", "Record")
    return w


def hub(w, op, **prefs):
    w.suite.link._handle({"op": op, "prefs": prefs, "actions": [], "states": {}})


def on_screen(w):
    """Every word One-Hand shows or gives a screen reader, widget by widget: the window, its
    badge and its menu, hidden parts too."""
    found = []
    for widget in [w, *w.findChildren(QWidget), w.badge, w.badge.label]:
        texts = [widget.accessibleName(), widget.accessibleDescription(), widget.toolTip()]
        if isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        if isinstance(widget, QComboBox):
            texts += [widget.itemText(i) for i in range(widget.count())]
        found.append((type(widget).__name__, *texts))
    found += [("menu", a.text()) for a in w._tray_menu.actions()] + [("tray", w.tray.toolTip())]
    return found


# Names, and words that read the same in Spanish.
SAME_EVERYWHERE = {APP_NAME, "Logic Pro", "Pro Tools", "Editor", "Tab", "Esc"}


def untranslated(english, spanish):
    assert len(english) == len(spanish)
    return [(e, s) for a, b in zip(english, spanish) for e, s in zip(a[1:], b[1:])
            if e == s and LETTERS.search(e) and e not in SAME_EVERYWHERE]


def test_the_windows_in_spanish(make, monkeypatch):
    english = busy(make())
    english_setup = make(error="not allowed", permissions={"Accessibility": False, "Input Monitoring": False})
    monkeypatch.setattr(words, "_computer", "es")   # a computer in Spanish, before the hub says anything
    w = busy(make())
    setup = make(error="not allowed", permissions={"Accessibility": False, "Input Monitoring": False})

    assert untranslated(on_screen(english), on_screen(w)) == []
    assert untranslated(on_screen(english_setup), on_screen(setup)) == []
    assert w.power.text() == "Modo una mano ACTIVADO" and w.power.accessibleName() == w.power.text()
    assert w.status.text() == ("Pruébalo aquí: pulsa las teclas de la mano izquierda que ves abajo para saber "
                               "qué hacen.")
    assert w.practice.text() == "E → Grabar. En Logic Pro pulsa R."
    assert w.badge.label.text() == "MODO UNA MANO ACTIVADO  ·  Mano izquierda  ·  esperando a tu DAW"
    assert "Texto más grande" in [b.text() for b in w.findChildren(QCheckBox)]
    assert w.app_pick.accessibleName() == "Mostrar el mapa de teclas de"
    assert next(c for _, _, c in w.cards if c.key == "1").accessibleName() == "Tecla 1: Ir al principio, pulsa Intro"
    assert w.hand_buttons["left"].text() == "Mano izquierda"
    assert [a.text() for a in w._tray_menu.actions() if a.text()][0] == "Desactivar el modo una mano"
    page = setup.permission_page
    _, tick, btn = page.steps["Input Monitoring"]
    assert tick.accessibleName() == "Monitorización de entrada: todavía no permitido"
    assert btn.text() == "Abrir ajustes de Monitorización de entrada"
    assert btn.accessibleName() == "Abrir ajustes de Monitorización de entrada en Ajustes del Sistema"
    assert page.status.text() == "Esperando a que los actives. Esta página se actualiza sola."


def test_changing_language_changes_the_words_in_place(make, monkeypatch):
    w = busy(make())
    w.show()
    w.activateWindow()
    for _ in range(100):
        if QApplication.activeWindow() is w:
            break
        QTest.qWait(20)
    larger = next(b for b in w.findChildren(QCheckBox) if b.text() == "Larger text")
    larger.setFocus(Qt.FocusReason.TabFocusReason)
    assert QApplication.focusWidget() is larger
    english = on_screen(w)

    hub(w, "welcome", language="es")   # the suite is in Spanish
    assert QApplication.focusWidget() is larger and larger.text() == "Texto más grande"   # focus stays put
    assert w.sent[-1] == ("prefs.applied", {"textScale": 1.0, "highContrast": False, "reduceMotion": False,
                                            "language": "es"})
    switched = on_screen(w)
    monkeypatch.setattr(words, "_computer", "es")
    assert switched == on_screen(busy(make()))   # just as if it had opened in Spanish

    hub(w, "prefs", language="en")
    assert on_screen(w) == english and QApplication.focusWidget() is larger


def test_the_same_language_again_changes_no_words(make, monkeypatch):
    w = busy(make())
    hub(w, "welcome", language="es")
    events = []
    monkeypatch.setattr(QAccessible, "updateAccessibility", lambda e: events.append(e.type()))
    before = on_screen(w)
    hub(w, "prefs", language="es", textScale=1.5)   # another setting changed, not the language
    assert on_screen(w) == before
    assert not [e for e in events if e in (QAccessible.Event.NameChanged, QAccessible.Event.DescriptionChanged,
                                           QAccessible.Event.ValueChanged)]


def test_a_problem_off_a_mac_is_said_in_the_new_language(make, monkeypatch):
    monkeypatch.setattr(SimBackend, "platform", "windows")
    w = make(error=platform_sim.UNSUPPORTED)
    assert w.banner_text.text().startswith("Keyboard control works on Mac and Windows.")
    hub(w, "welcome", language="es")
    assert w.banner_text.text() == ("El control del teclado funciona en Mac y Windows. Este equipo solo puede "
                                    "mostrar la ventana.\n\nEste equipo aún no es compatible. La ventana funciona, "
                                    "pero las teclas no cambian.")

    w = make(error=t("Could not watch the keyboard (error {code}).", code=5))   # as Windows says it, in Spanish
    assert w.banner_text.text().startswith("No se pudo leer el teclado (error 5).")
    hub(w, "welcome", language="en")
    assert w.banner_text.text().startswith("Could not watch the keyboard (error 5).")
