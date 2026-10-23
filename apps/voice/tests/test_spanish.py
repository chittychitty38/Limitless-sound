"""Voice's windows in the language it's set to: every word they show has Spanish, every window
built in Spanish shows no English, and the words change in place when the language changes in
Settings or in Limitless Sound. What the windows suggest saying is in the language Voice listens
in. No mic, no real OS, no hub, no speech model: a model folder is faked where one's needed."""
import ast
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

# first: it sets up a private config folder and an offscreen screen
from test_setup import SPANISH_MODEL, make

# isort: split
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QPushButton,
                               QSystemTrayIcon, QWidget)

from limitless_voice import app as app_module, onboarding, words
from limitless_voice.app import CommandsDialog, SettingsDialog
from limitless_voice.engine import Engine
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs
from limitless_voice.hud import STATES
from limitless_voice.language import ENGLISH, available, load
from limitless_voice.platforms.dryrun import DryRunPlatform
from limitless_voice.settings import data_dir
from limitless_voice.words import ui

ES = load("es")
PACKAGE = Path(words.__file__).parent
CODE = sorted([*PACKAGE.glob("*.py"), *PACKAGE.glob("platforms/*.py")])
# The code that puts words in windows, or gives them to a screen reader
WINDOW_CODE = [PACKAGE / name for name in ("app.py", "onboarding.py", "hud.py", "look.py", "audio.py")] + \
    sorted(PACKAGE.glob("platforms/*.py"))
ENGLISH_MODEL = data_dir() / "models" / "vosk-model-small-en-us-0.15"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
TAG = re.compile(r"<[^>]+>")
LETTERS = re.compile(r"[^\W\d_]{2}")
# Names, the same in every language (each language's name is in itself)
NAMES = ["Limitless Voice", "Limitless Sound", "Logic Pro", "Pro Tools", *(name for _, name in available())]


def has_words(text):
    """Whether text has words to translate, past its markup, {names} and &nbsp;."""
    return bool(LETTERS.search(re.sub(r"&\w+;", "", PLACEHOLDER.sub("", TAG.sub("", text)))))


def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def literals(called, paths=CODE):
    """Every call written called("…"), like ui.text("…") or phrase("…"): where, the words, and the
    {names} it fills in (None if it can't tell)."""
    for path in paths:
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == called \
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names = None if any(k.arg is None for k in node.keywords) else {k.arg for k in node.keywords}
                yield f"{path.relative_to(PACKAGE)}:{node.lineno}", node.args[0].value, names


def suggested():
    """Everything the windows suggest saying, in English: phrase("…"), and the setup guide's list."""
    found = [en for _, en, _ in literals("phrase")]
    found += [say for say, _ in onboarding.STARTER_COMMANDS]
    return sorted(set(found))


class Languages(unittest.TestCase):
    """The windows' language goes back to English after each test."""

    def setUp(self):
        self.addCleanup(words.listen_in, ENGLISH)
        self.addCleanup(words.use, "en")


# ---- the words -----------------------------------------------------------------------------

class Words(Languages):
    def test_every_word_in_the_windows_has_spanish(self):
        found = list(literals("ui.text"))
        self.assertGreater(len(found), 120)
        missing = [f"{where} {en!r}" for where, en, _ in found if has_words(en) and en not in ES.texts]
        self.assertEqual(missing, [], "no Spanish for these")
        unfilled = [f"{where} {en!r}" for where, en, names in found
                    if names is not None and names != set(PLACEHOLDER.findall(en))]
        self.assertEqual(unfilled, [], "placeholders not filled in")

    def test_spanish_keeps_every_placeholder_tag_and_access_key(self):
        for _, en, _ in literals("ui.text"):
            es = ES.texts.get(en)
            if es is None:
                continue
            self.assertEqual(sorted(PLACEHOLDER.findall(en)), sorted(PLACEHOLDER.findall(es)), en)
            self.assertEqual(sorted(TAG.findall(en)), sorted(TAG.findall(es)), en)
            self.assertEqual(len(re.findall(r"&\w", en)), len(re.findall(r"&\w", es)), en)   # Alt+M, Alt+H

    def test_words_from_elsewhere_have_spanish(self):
        # the setup guide's list says what each command does, and Settings names the speech models
        used = {what for _, what in onboarding.STARTER_COMMANDS}
        used |= {m["label"] for code, _ in available() for m in load(code).models.values()}
        used |= {label for _, label in STATES.values()}   # the floating display's listening states
        self.assertEqual(sorted(used - ES.texts.keys()), [])

    def test_what_the_windows_suggest_saying_works_in_spanish(self):
        """Each command a window suggests does in Spanish what it does in English, in Logic Pro
        and in Pro Tools: the same keys, or nothing in both."""
        found = suggested()
        self.assertGreater(len(found), 8)
        for english in found:
            self.assertIn(english, ES.texts, "no Spanish to suggest for")
            spanish = ES.texts[english]
            pairs = list(zip(english.split("/"), spanish.split("/"), strict=True))
            for en, es in pairs:
                for app in ("Logic Pro", "Pro Tools"):
                    self.assertEqual(self.run_command(ES, es.strip(), app), self.run_command(ENGLISH, en.strip(), app),
                                     f"{es!r} for {en!r} in {app}")

    @staticmethod
    def run_command(lang, said, app):
        p = DryRunPlatform("mac", app=app)
        packs = lang.translate(load_packs([DEFAULT_PACK_DIR], "mac"))
        r = Engine(p, packs, own_names=["Limitless Voice"], language=lang).handle(said.lower(), said.lower())
        return r.handled, r.kind, [e[1] for e in p.log if e[0] in ("press", "type", "open")]

    def test_no_english_reaches_the_screen_without_ui_text(self):
        shown_by = {"setText", "setAccessibleName", "setAccessibleDescription", "setToolTip", "setWindowTitle",
                    "setPlaceholderText", "setItemText", "showMessage", "addAction", "addItem", "addItems",
                    "insertItem", "addRow", "addButton", "LiveText", "QLabel", "QPushButton", "QCheckBox", "QAction",
                    "QMessageBox", "QProgressDialog", "label", "add_item", "add_row", "_title", "_body", "_status",
                    "_button", "_show_did", "on_mic_error", "on_error", "announce", "say", "show", "keep",
                    "show_message", "warning", "question", "information", "NotSupported", "RuntimeError"}

        def raw(node):
            """Words written straight into an argument, not through ui.text()."""
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return [node.value]
            if isinstance(node, ast.JoinedStr):
                return ["".join(v.value for v in node.values if isinstance(v, ast.Constant))]
            if isinstance(node, ast.IfExp):
                return raw(node.body) + raw(node.orelse)
            if isinstance(node, ast.BoolOp):
                return [w for v in node.values for w in raw(v)]
            if isinstance(node, ast.BinOp):   # "✓ " + text
                return raw(node.left) + raw(node.right)
            return []

        found = []
        for path in WINDOW_CODE:
            for node in ast.walk(tree(path)):
                called = getattr(node, "func", None)
                if isinstance(node, ast.Call) and (getattr(called, "id", None) or getattr(called, "attr", None)) \
                        in shown_by:
                    for arg in [*node.args, *(k.value for k in node.keywords)]:
                        for text in raw(arg):
                            if has_words(re.sub("|".join(NAMES), "", text)):
                                found.append(f"{path.name}:{node.lineno} {text[:70]!r}")
        self.assertEqual(found, [], "words shown without ui.text()")

    def test_t_fills_in_and_says_it_again_in_another_language(self):
        said = ui.text("Using {microphone}", microphone=ui.text("System default microphone"))
        self.assertEqual(said, "Using System default microphone")
        self.assertEqual(ui.text("{name} (default)", name="Apple Virtual Sound Device"),
                         "Apple Virtual Sound Device (default)")
        self.assertTrue(words.use("es"))
        self.assertFalse(words.use("es"))
        self.assertEqual(words.again(said), "Usando Micrófono predeterminado del sistema")
        self.assertEqual(ui.text("{name} (default)", name="Apple Virtual Sound Device"),
                         "Apple Virtual Sound Device (predeterminado)")   # a device's name is its own
        self.assertEqual(ui.text("Not in the table"), "Not in the table")      # no Spanish: it stays English
        self.assertEqual(words.again("plain words"), "plain words")

    def test_what_to_say_is_in_the_language_listened_in(self):
        hint = ui.text('Say something, like "{phrase}".', phrase=words.phrase("what can I say"))
        words.use("es")   # the windows in Spanish, still listening in English: its model isn't here yet
        self.assertEqual(words.again(hint), 'Di algo, por ejemplo "what can I say".')
        words.listen_in(ES)   # and now it is
        self.assertEqual(words.again(hint), 'Di algo, por ejemplo "qué puedo decir".')


# ---- the windows ---------------------------------------------------------------------------

class Windows(Languages):
    """Voice's windows with a menu bar icon, in a computer that lists no microphones: a
    microphone's name is its own, the same in every language ("Apple Virtual Sound Device" on a
    CI Mac)."""

    def setUp(self):
        super().setUp()
        for patch in (mock.patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True),
                      mock.patch.object(app_module, "list_input_devices", return_value=[]),
                      mock.patch.object(onboarding, "list_input_devices", return_value=[])):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, SPANISH_MODEL, True)
        self.addCleanup(shutil.rmtree, ENGLISH_MODEL, True)

    def make(self, language=""):
        w, p, s = make(mic="granted", control=False, language=language)   # keys not allowed yet
        w._check_permissions()
        self.addCleanup(self.close, w)
        return w

    @staticmethod
    def close(w):
        if w.wizard is not None:
            w.wizard.reject()
        w.shutdown()
        w.hide()
        if w.tray:
            w.tray.hide()
        w.deleteLater()

    @staticmethod
    def hub(w, op="prefs", **prefs):
        w.suite.link._handle({"op": op, "prefs": {"textScale": 1.0, "highContrast": False, "reduceMotion": False,
                                                  **prefs}})

    def busy(self, w):
        """Every window open and saying the most it says: a command heard, a microphone problem,
        the floating display, What you can say, Settings, and the setup guide on every page."""
        undo = "deshacer" if w.lang.code == "es" else "undo"   # Pro Tools is in front
        w.on_heard(undo, undo)
        w.on_mic_error(ui.text("Microphone problem: {error}. Retrying…", error="-9996"))
        w.hud.show_message(undo, w.did_label.text())
        CommandsDialog(w, w.engine)
        settings = SettingsDialog(w, w.settings)
        settings.language.setCurrentIndex(settings.language.findData("es"))   # the same models in both
        w.show_setup()
        for i in range(len(w.wizard.pages)):
            w.wizard._show(i)
        w.wizard._show(3)
        asked = words.phrase("what can I say")
        w.on_heard(asked, asked)
        return w

    @staticmethod
    def on_screen(w):
        """Every word Voice shows or gives a screen reader, widget by widget: the main window and
        every window it opened, the floating display, and the menu bar menu. Hidden parts too."""
        found = []
        for widget in [w, *w.findChildren(QWidget), w.hud, *w.hud.findChildren(QWidget)]:
            texts = [widget.accessibleName(), widget.accessibleDescription(), widget.toolTip()]
            if isinstance(widget, (QLabel, QAbstractButton)):
                texts.append(widget.text())
            if isinstance(widget, QLineEdit):
                texts.append(widget.placeholderText())
            if isinstance(widget, QComboBox):
                texts += [widget.itemText(i) for i in range(widget.count())]
            if widget.isWindow():
                texts.append(widget.windowTitle())
            found.append((type(widget).__name__, *texts))
        found += [("menu", a.text()) for a in w.tray_menu.actions()] + [("tray", w.tray.toolTip())]
        return found

    def untranslated(self, english, spanish):
        self.assertEqual([e[0] for e in english], [s[0] for s in spanish])   # the same windows
        return [(e, s) for a, b in zip(english, spanish) for e, s in zip(a[1:], b[1:], strict=True)
                if e == s and has_words(re.sub("|".join(NAMES), "", e))]

    def test_every_window_in_spanish(self):
        english = self.on_screen(self.busy(self.make()))
        w = self.busy(self.make(language="es"))   # chosen in Settings, its speech model here
        self.assertEqual(self.untranslated(english, self.on_screen(w)), [])

        # what a Spanish speaker reads, and VoiceOver says
        self.assertEqual(w.listen_btn.accessibleName(), 'Escuchando: di "a dormir" para hacer una pausa')
        self.assertEqual(w.heard_label.text(), "Oído: “deshacer”")
        self.assertEqual(w.target_label.text(), "Enviando comandos a: Pro Tools")
        self.assertEqual(w.permission_text.text(), "<b>Permite que Limitless Voice controle el equipo</b><br>"
                                                   "Abre los ajustes de Accesibilidad, activa Limitless Voice y "
                                                   "vuelve aquí. Es lo que permite que los comandos de voz pulsen "
                                                   "teclas en Logic y Pro Tools.")
        self.assertEqual(w.mic_error.text(), "Problema con el micrófono: -9996. Reintentando…")
        self.assertEqual(w.mic_combo.itemText(0), "Micrófono predeterminado del sistema")
        self.assertEqual([a.text() for a in w.tray_menu.actions() if a.text()],
                         ['Escuchando: di "a dormir" para hacer una pausa', "Dejar de escuchar",
                          "Mostrar Limitless Voice", "¿Qué puedo decir?", "Repetir la configuración…",
                          "Salir de Limitless Voice"])
        self.assertEqual(w.hud.state_label.text(), "Escuchando")
        settings = w.findChild(SettingsDialog)
        self.assertEqual(settings.windowTitle(), "Ajustes")
        languages = [settings.language.itemText(i) for i in range(settings.language.count())]
        self.assertEqual(languages[:3], ["Igual que Limitless Sound (English)", "English (descarga de 40 MB)",
                                         "Español"])   # then any other language Voice has
        self.assertEqual(settings.model.itemText(0), "Español, rápido (instalado)")
        self.assertEqual(sorted(b.text() for b in settings.findChildren(QPushButton)), ["Cancelar", "Guardar"])
        commands = w.findChild(CommandsDialog)
        self.assertEqual(commands.windowTitle(), "Lo que puedes decir")
        self.assertIn("a dormir / despierta   (siempre)", commands.rows)
        wizard = w.wizard
        self.assertEqual(wizard.windowTitle(), "Configurar Limitless Voice")
        self.assertEqual(wizard.next_btn.text(), "Continuar")
        self.assertEqual(wizard.pages[3].result.text(), "✓ Oído: “qué puedo decir”. Tu micrófono funciona.")
        ready = [lbl.text() for lbl in wizard.pages[5].findChildren(QLabel)]
        self.assertIn("<b>“ir al compás treinta y dos”</b> &nbsp; <span style='color:gray'>ir a cualquier punto"
                      "</span>", ready)
        self.assertIn("Vamos a probar el micrófono. Di: qué puedo decir.", w.speaker.said)

    def test_changing_language_changes_the_words_in_place(self):
        (SPANISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        (ENGLISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        w = self.make()
        w._show_did(w.lang.text("Listening in {language}", language="English"))   # as after a change
        w._track_focus()   # as its timer does
        w.show()
        w.activateWindow()
        for _ in range(100):
            if QApplication.activeWindow() is w:
                break
            QTest.qWait(20)
        settings = next(b for b in w.findChildren(QPushButton) if b.text() == "Settings")
        settings.setFocus(Qt.TabFocusReason)
        self.assertIs(QApplication.focusWidget(), settings)
        english = self.on_screen(w)

        self.hub(w, "welcome", language="es")   # Limitless Sound is in Spanish, and so is Voice now
        self.assertEqual((w.lang.code, settings.text()), ("es", "Ajustes"))
        self.assertIs(QApplication.focusWidget(), settings)   # focus stays put
        self.assertEqual(self.on_screen(w), self.on_screen(self.make(language="es")))   # as if opened in Spanish

        self.hub(w, language="en")
        self.assertEqual(self.on_screen(w), english)
        self.assertIs(QApplication.focusWidget(), settings)

    def test_open_windows_change_too(self):
        (SPANISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        w = self.make()
        settings = SettingsDialog(w, w.settings)
        commands = CommandsDialog(w, w.engine)
        w.show_setup()
        self.hub(w, "welcome", language="es")
        self.assertEqual(settings.windowTitle(), "Ajustes")
        self.assertEqual(sorted(b.text() for b in settings.findChildren(QPushButton)), ["Cancelar", "Guardar"])
        self.assertEqual(commands.search.placeholderText(), "Buscar comandos")
        self.assertIn("(siempre)", commands.list.item(commands.list.count() - 3).text())
        self.assertEqual(w.wizard.windowTitle(), "Configurar Limitless Voice")
        self.assertEqual(w.wizard.step_label.text(), "Paso 1 de 6")
        welcome = [lbl.text() for lbl in w.wizard.pages[0].findChildren(QLabel)]
        self.assertTrue(any("Di <b>“ir al compás treinta y dos”</b>" in text for text in welcome), welcome)

    def test_the_same_language_again_changes_no_words(self):
        (SPANISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        w = self.make()
        self.hub(w, "welcome", language="es")
        before = self.on_screen(w)
        again, events = [], []
        w.retranslate = lambda: again.append(1)
        with mock.patch.object(QAccessible, "updateAccessibility", lambda e: events.append(e.type())):
            self.hub(w, language="es", textScale=1.5)   # another setting changed, not the language
        self.assertEqual(again, [])
        self.assertEqual(self.on_screen(w), before)
        self.assertNotIn(QAccessible.NameChanged, events)
        self.assertNotIn(QAccessible.DescriptionChanged, events)

    def test_spanish_chosen_before_its_model_is_here(self):
        """The windows change at once; what they suggest saying is English until Spanish is here."""
        w = self.make()
        w.settings.language = "es"
        w.apply_language()   # as Settings does when it's saved
        self.assertEqual(w.lang.code, "en")
        self.assertEqual(w.listen_btn.text(), 'Escuchando: di "go to sleep" para hacer una pausa')
        self.assertEqual(w.heard_label.text(), 'Di algo, por ejemplo "what can I say".')
        self.assertEqual(w.language_download.text(), "Descargar español (39 MB)")
        with mock.patch.object(app_module, "ensure_model", side_effect=lambda *a, **k:
                               (SPANISH_MODEL / "conf").mkdir(parents=True) or SPANISH_MODEL):
            w.language_download.click()
        self.assertEqual(w.lang.code, "es")
        self.assertEqual(w.listen_btn.text(), 'Escuchando: di "a dormir" para hacer una pausa')
        self.assertEqual(w.heard_label.text(), 'Di algo, por ejemplo "qué puedo decir".')

    def test_the_permission_box_is_said_once_in_either_language(self):
        (SPANISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        w = self.make()
        self.assertEqual(w.speaker.said, ["Allow Limitless Voice to control the computer"])
        self.hub(w, "welcome", language="es")
        w._check_permissions()
        self.assertEqual(w.speaker.said.count("Allow Limitless Voice to control the computer"), 1)
        self.assertNotIn("Permite que Limitless Voice controle el equipo", w.speaker.said)   # said already
        self.assertTrue(w.permission_text.text().startswith("<b>Permite que Limitless Voice controle el equipo"))


if __name__ == "__main__":
    unittest.main()
