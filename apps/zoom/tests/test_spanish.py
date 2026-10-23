"""Limitless Zoom in the suite's language: every word it shows or says has Spanish, every window
shows it, and the words change in place when the musician picks another language in Limitless
Sound. Voice commands in Spanish are test_voice_language.py's."""

import ast
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel, QSystemTrayIcon,  # noqa: E402
                               QWidget)

from limitless_zoom import voice, words  # noqa: E402
from limitless_zoom.actions import LABELS, PANEL_BUTTONS  # noqa: E402
from limitless_zoom.app import ZoomApp  # noqa: E402
from limitless_zoom.keymaps import TARGETS  # noqa: E402
from limitless_zoom.keys import format_key  # noqa: E402
from limitless_zoom.settings import Settings  # noqa: E402
from limitless_zoom.suite import EXTRA  # noqa: E402
from limitless_zoom.ui import KeyCaptureDialog  # noqa: E402
from limitless_zoom.words import SPANISH, t  # noqa: E402
from test_ui import PermBackend  # noqa: E402

PACKAGE = Path(words.__file__).parent
PLACEHOLDER = re.compile(r"\{(\w+)\}")
LETTERS = re.compile(r"[^\W\d_]{2}")
# Names, and words that read the same in Spanish.
SAME_EVERYWHERE = {"Limitless Zoom", "Logic Pro", "GarageBand", "Pro Tools", "Ableton Live", "Tab",
                   "{name}: {state}"}


# ---- the words ---------------------------------------------------------------------------

def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def calls_to_t():
    """Every t("…") in Zoom: where, the English, and the names it fills in (None if it can't tell)."""
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names = None if any(k.arg is None for k in node.keywords) else {k.arg for k in node.keywords}
                yield f"{path.name}:{node.lineno}", node.args[0].value, names


def mac_permissions():
    """What MacBackend says macOS must allow, read from platforms.py (it only runs on a Mac)."""
    found = []
    for node in ast.walk(tree(PACKAGE / "platforms.py")):
        if isinstance(node, ast.Dict):
            d = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            if {"title", "why"} <= d.keys():
                found.append({k: d[k].value for k in ("key", "title", "why", "required")})
    return found


def test_every_word_in_the_code_has_spanish():
    found = list(calls_to_t())
    assert len(found) > 100
    missing = [f"{where} {en!r}" for where, en, _ in found if en not in SPANISH]
    assert not missing, "no Spanish for:\n" + "\n".join(missing)
    unfilled = [f"{where} {en!r}" for where, en, names in found
                if names is not None and names != set(PLACEHOLDER.findall(en))]
    assert not unfilled, "placeholders not filled in:\n" + "\n".join(unfilled)


def test_actions_buttons_and_permissions_have_spanish():
    # Not written as t("…"): the actions' words, the panel's buttons, what macOS must allow.
    assert len(mac_permissions()) == 4
    used = {*LABELS.values(), *EXTRA.values(), *(label for _, label in PANEL_BUTTONS)}
    used |= {t["name"] for t in TARGETS.values()} - SAME_EVERYWHERE
    used |= {p[part] for p in mac_permissions() for part in ("title", "why")}
    assert not sorted(used - SPANISH.keys()), sorted(used - SPANISH.keys())


def test_spanish_keeps_every_placeholder_and_tag():
    for en, es in SPANISH.items():
        assert sorted(PLACEHOLDER.findall(en)) == sorted(PLACEHOLDER.findall(es)), en
        assert sorted(re.findall(r"<[^>]+>", en)) == sorted(re.findall(r"<[^>]+>", es)), en


# Calls that put words on screen, or say them out loud.
SHOWN_BY = {"setText", "setAccessibleName", "setAccessibleDescription", "setToolTip", "setWindowTitle",
            "setTitle", "showMessage", "addAction", "addMenu", "addItem", "setItemText", "show_text", "feedback",
            "_status", "_voice_status", "set_voice_status", "capture_key", "say", "label", "LiveText", "Toast",
            "QLabel", "QPushButton", "QCheckBox", "QAction", "DwellButton", "KeyCaptureDialog"}


def raw_words(node):
    """Words written straight into an argument, not through t()."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value for v in node.values if isinstance(v, ast.Constant))]
    if isinstance(node, ast.IfExp):
        return raw_words(node.body) + raw_words(node.orelse)
    if isinstance(node, ast.BoolOp):
        return [w for v in node.values for w in raw_words(v)]
    return []


def test_no_english_reaches_the_screen_without_t():
    raw = []
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in SHOWN_BY:
                for arg in [*node.args, *(k.value for k in node.keywords if k.arg in ("about", "text", "title"))]:
                    for text in raw_words(arg):
                        text = re.sub(r"<[^>]*>", "", text)   # markup isn't words
                        if LETTERS.search(re.sub("|".join(SAME_EVERYWHERE), "", text)):
                            raw.append(f"{path.name}:{node.lineno} {text[:70]!r}")
    assert not raw, "words shown without t():\n" + "\n".join(raw)


def test_t_fills_in_and_says_it_again_in_another_language(monkeypatch):
    said = t("Voice: heard “{text}”", text=t("{heard} (not sure, ignored)", heard="zoom on"))
    assert said == "Voice: heard “zoom on (not sure, ignored)”"
    monkeypatch.setattr(words, "_suite", "es")
    assert words.again(said) == "Voz: oí «zoom on (sin certeza, se ignora)»"   # what was heard stays as heard
    assert format_key("right_alt", "mac") == "Opción derecha" and format_key(None) == "sin asignar"


def test_the_language_is_the_suites_else_the_computers(monkeypatch):
    assert words.tag("es-419") == "es" and words.tag("pt-BR") is None
    assert words.system_language(lambda: ["fr-FR", "es-ES"]) == "es"
    monkeypatch.setattr(words, "_computer", "es")
    assert words.language() == "es"
    assert words.follow("en") and words.language() == "en"
    assert not words.follow(None) and words.language() == "en"   # a hub that sends none keeps the last


# ---- the windows -------------------------------------------------------------------------

MAC = mac_permissions()


class MacLike(PermBackend):
    """A Mac with Accessibility still to allow, its permissions worded as MacBackend words them."""

    def permissions(self):
        state = {"accessibility": "ok" if self.allowed else "missing", "input": "ok", "microphone": "missing",
                 "zoom": "unknown"}
        return [{**p, "state": state[p["key"]]} for p in MAC]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))   # the menu too
    # The computer's microphones ("Apple Virtual Sound Device" on a CI Mac) are names, the same in
    # every language, so leave them out as Linux does.
    monkeypatch.setattr(voice, "list_microphones", lambda: [])
    made = []

    def make():
        s = Settings(tmp_path / f"settings{len(made)}.json")
        s["speak"] = False
        app = ZoomApp(s, MacLike(), use_keys=False, use_voice=False, use_tray=True)
        app.sent = []
        app.suite.link._send = lambda msg: app.sent.append(msg) or True   # no hub: keep what it would send
        app.start()   # first run: the panel, then setup
        QTest.qWait(400)
        assert app.setup_window is not None
        made.append(app)
        return app

    yield make
    for app in made:
        for w in (app.setup_window, app.panel, app.toast, app.badge, app.tray):
            w.hide()
        app.poll.stop()
        app.perm_timer.stop()
        # On Windows a second server can take the same pipe name and the first one still gets
        # the calls: a later test's "--do out" would land in this app.
        app.server.close()


def busy(app):
    """Zoom has zoomed, the zoom keys are on, voice is listening and heard something."""
    app.run("in")
    app.run("keys")
    app._voice_status(t("Listening on {name}", name="MacBook Pro Microphone"))
    app._heard("zoom in")
    app._heard(t("{heard} (not sure, ignored)", heard="zoom on"))
    return app


def hub(app, op, **prefs):
    app.suite.link._handle({"op": op, "prefs": prefs, "actions": [], "states": {}})


def on_screen(app):
    """Every word Zoom shows or gives a screen reader, widget by widget, in every window and its
    menu, hidden parts too."""
    found = []
    for window in (app.toast, app.badge, app.panel, app.setup_window):
        for w in [window, *window.findChildren(QWidget)]:
            texts = [w.accessibleName(), w.accessibleDescription(), w.toolTip()]
            if isinstance(w, (QLabel, QAbstractButton)):
                texts.append(w.text())
            if isinstance(w, QComboBox):
                texts += [w.itemText(i) for i in range(w.count())]
            if w.isWindow():
                texts.append(w.windowTitle())
            found.append((type(w).__name__, *texts))
    found += [("menu", a.text()) for a in app._menu.actions()] + [("tray", app.tray.toolTip())]
    return found


def untranslated(english, spanish):
    assert len(english) == len(spanish)
    return [(e, s) for a, b in zip(english, spanish) for e, s in zip(a[1:], b[1:])
            if e == s and LETTERS.search(re.sub("|".join(SAME_EVERYWHERE), "", e))]


def test_every_window_in_spanish(make, monkeypatch):
    english = on_screen(busy(make()))
    english_dialog = KeyCaptureDialog(t("Switch"), t("Press your switch now."), lambda cb: None)
    monkeypatch.setattr(words, "_computer", "es")   # a computer in Spanish, before the hub says anything
    app = busy(make())
    dialog = KeyCaptureDialog(t("Switch"), t("Press your switch now."), lambda cb: None)

    assert untranslated(english, on_screen(app)) == []
    assert dialog.windowTitle() == "Pulsador" and dialog.label.text().startswith("Presiona ahora tu pulsador.")
    assert english_dialog.label.text() != dialog.label.text()
    assert app.toast.label.text() == "Teclas de zoom activadas"   # the last thing Zoom did
    assert app.badge.label.text() == "TECLAS DE ZOOM ACTIVADAS"
    panel, setup = app.panel, app.setup_window
    assert [b.accessibleName() for b in panel.buttons[:2]] == ["Alejar", "Acercar"]
    assert panel.buttons[1].text() == "+  Acercar" and panel.scan_button.text() == "Barrido: no"
    assert panel.keys_label.text().startswith("Teclas de zoom ACTIVADAS: E acercar, Q alejar")
    assert panel.voice_label.text() == "Voz: oí «zoom on (sin certeza, se ignora)»"
    assert setup.windowTitle() == "Configurar Limitless Zoom"
    assert setup.voice_status.text() == "Escuchando en MacBook Pro Microphone"
    assert setup.heard.text() == "Oí: «zoom on (sin certeza, se ignora)»"
    assert setup.start_btn.text() == "Empezar (aún falta Accesibilidad)"
    mark, text, btn = setup.perm_rows["accessibility"]
    assert mark.accessibleName() == "Accesibilidad: todavía no permitido"
    assert btn.accessibleName() == "Permitir Accesibilidad"
    assert "Monitorización de entrada" in setup.perm_rows["input"][1].text()
    assert setup.perm_rows["zoom"][2].text() == "Abrir Ajustes…"
    assert setup.mic.itemText(0) == "Micrófono predeterminado del sistema"
    assert app.panel.status.text() == "Necesita Accesibilidad. Abre «Configuración y ayuda» en la barra de menús."
    assert [a.text() for a in app._menu.actions()][:2] == ["Mostrar u ocultar el panel de zoom",
                                                           "Teclas de zoom activadas"]
    dialog.reject()
    english_dialog.reject()


def test_changing_language_changes_the_words_in_place(make, monkeypatch):
    app = busy(make())
    english = on_screen(app)
    focus = app.setup_window.change_btn
    app.setup_window.activateWindow()
    for _ in range(100):
        if QApplication.activeWindow() is app.setup_window:
            break
        QTest.qWait(20)
    focus.setFocus()
    assert QApplication.focusWidget() is focus

    hub(app, "welcome", language="es")   # the suite is in Spanish
    switched = on_screen(app)
    assert focus.text() == "Usar otra tecla…" and QApplication.focusWidget() is focus   # focus stays put
    applied = [m["value"] for m in app.sent if m["op"] == "state" and m["key"] == "prefs.applied"]
    assert applied[-1] == {"language": "es"}   # only what the hub sent, with the value Zoom uses
    monkeypatch.setattr(words, "_computer", "es")
    assert switched == on_screen(busy(make()))   # just as if it had opened in Spanish

    hub(app, "prefs", language="en")
    assert on_screen(app) == english


def test_the_same_language_again_changes_no_words(make):
    app = busy(make())
    hub(app, "welcome", language="es")
    before = on_screen(app)
    again = []
    app.retranslate = lambda: again.append(1)
    hub(app, "prefs", language="es", dwellMs=1200)   # another setting changed, not the language
    assert again == [] and on_screen(app) == before


def test_answers_to_the_suite_are_in_its_language(make):
    app = make()
    hub(app, "welcome", language="es")
    assert app.suite.invoke("fit", {}, "voice") == (True, "Ajustar a la ventana")
    assert app.suite.invoke("keysOn", {}, "voice") == (True, "Teclas de zoom activadas")
    assert app.suite.invoke("sideways", {}, "x") == (False, "Limitless Zoom no tiene la acción 'sideways'.")
    app.backend.front = "com.ableton.live"
    app.run("taller")
    assert app.toast.label.text() == "Pistas más altas no está disponible en Ableton Live"
