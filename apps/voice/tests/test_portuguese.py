"""Voice's windows in Brazilian Portuguese, checked the way test_spanish.py checks them in Spanish:
every word they show has Portuguese with the same placeholders, tags and access keys; what they
suggest saying works in Portuguese; a window built in Portuguese shows no English; the words
change in place when the language changes; and the longer Portuguese words still fit, with no
button, choice or line cut off. No mic, no real OS, no hub, no speech model: a model folder is
faked where one's needed (the Portuguese model keeps everything in one folder)."""
import re
import shutil
from unittest import mock

# first: it sets up a private config folder and an offscreen screen
import test_spanish as spanish
from test_setup import make

# isort: split
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QPushButton, QSystemTrayIcon, QWidget

from limitless_voice import app as app_module, onboarding, words
from limitless_voice.app import CommandsDialog, SettingsDialog
from limitless_voice.hud import STATES
from limitless_voice.language import ENGLISH, available, load
from limitless_voice.settings import data_dir
from limitless_voice.words import ui

PT = load("pt")
PORTUGUESE_MODEL = data_dir() / "models" / "vosk-model-small-pt-0.3"


class Words(spanish.Languages):
    def test_every_word_in_the_windows_has_portuguese(self):
        found = list(spanish.literals("ui.text"))
        self.assertGreater(len(found), 120)
        missing = [f"{where} {en!r}" for where, en, _ in found if spanish.has_words(en) and en not in PT.texts]
        self.assertEqual(missing, [], "no Portuguese for these")

    def test_portuguese_keeps_every_placeholder_tag_and_access_key(self):
        for _, en, _ in spanish.literals("ui.text"):
            pt = PT.texts.get(en)
            if pt is None:
                continue
            self.assertEqual(sorted(spanish.PLACEHOLDER.findall(en)), sorted(spanish.PLACEHOLDER.findall(pt)), en)
            self.assertEqual(sorted(spanish.TAG.findall(en)), sorted(spanish.TAG.findall(pt)), en)
            self.assertEqual(len(re.findall(r"&\w", en)), len(re.findall(r"&\w", pt)), en)   # Alt+M, Alt+H

    def test_words_from_elsewhere_have_portuguese(self):
        used = {what for _, what in onboarding.STARTER_COMMANDS}
        used |= {m["label"] for code, _ in available() for m in load(code).models.values()}
        used |= {label for _, label in STATES.values()}
        self.assertEqual(sorted(used - PT.texts.keys()), [])

    def test_what_the_windows_suggest_saying_works_in_portuguese(self):
        """Each command a window suggests does in Portuguese what it does in English, in Logic Pro
        and in Pro Tools: the same keys, or nothing in both."""
        for english in spanish.suggested():
            self.assertIn(english, PT.texts, "no Portuguese to suggest for")
            for en, pt in zip(english.split("/"), PT.texts[english].split("/"), strict=True):
                for app in ("Logic Pro", "Pro Tools"):
                    self.assertEqual(spanish.Words.run_command(PT, pt.strip(), app),
                                     spanish.Words.run_command(ENGLISH, en.strip(), app), f"{pt!r} for {en!r} in {app}")

    def test_what_to_say_is_in_the_language_listened_in(self):
        hint = ui.text('Say something, like "{phrase}".', phrase=words.phrase("what can I say"))
        words.use("pt")
        self.assertEqual(words.again(hint), 'Diga alguma coisa, por exemplo "what can I say".')
        words.listen_in(PT)
        self.assertEqual(words.again(hint), 'Diga alguma coisa, por exemplo "o que eu posso dizer".')


class Windows(spanish.Languages):
    """As test_spanish.Windows: every window, with a menu bar icon and no microphones listed."""

    def setUp(self):
        super().setUp()
        for patch in (mock.patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True),
                      mock.patch.object(app_module, "list_input_devices", return_value=[]),
                      mock.patch.object(onboarding, "list_input_devices", return_value=[])):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, PORTUGUESE_MODEL, True)
        self.addCleanup(shutil.rmtree, spanish.ENGLISH_MODEL, True)

    @staticmethod
    def downloaded():
        PORTUGUESE_MODEL.mkdir(parents=True, exist_ok=True)
        (PORTUGUESE_MODEL / "final.mdl").write_bytes(b"")   # never loaded

    def make(self, language=""):
        if language == "pt":
            self.downloaded()
        w, p, s = make(mic="granted", control=False, language=language)
        w._check_permissions()
        self.addCleanup(spanish.Windows.close, w)
        return w

    def busy(self, w):
        """Every window open, saying the most it says (test_spanish.Windows.busy), with Settings
        on Portuguese so its speech models are the same in both."""
        undo = "desfazer" if w.lang.code == "pt" else "undo"
        w.on_heard(undo, undo)
        w.on_mic_error(ui.text("Microphone problem: {error}. Retrying…", error="-9996"))
        w.hud.show_message(undo, w.did_label.text())
        CommandsDialog(w, w.engine)
        settings = SettingsDialog(w, w.settings)
        settings.language.setCurrentIndex(settings.language.findData("pt"))
        w.show_setup()
        for i in range(len(w.wizard.pages)):
            w.wizard._show(i)
        w.wizard._show(3)
        asked = words.phrase("what can I say")
        w.on_heard(asked, asked)
        return w

    def test_every_window_in_portuguese(self):
        english = spanish.Windows.on_screen(self.busy(self.make()))
        w = self.busy(self.make(language="pt"))
        self.assertEqual(spanish.Windows.untranslated(self, english, spanish.Windows.on_screen(w)), [])
        self.assertEqual(w.listen_btn.accessibleName(), 'Ouvindo: diga "vai dormir" para pausar')
        self.assertEqual(w.heard_label.text(), "Ouvido: “desfazer”")
        self.assertEqual(w.target_label.text(), "Enviando comandos para: Pro Tools")
        self.assertEqual(w.mic_error.text(), "Problema com o microfone: -9996. Tentando de novo…")
        self.assertEqual([a.text() for a in w.tray_menu.actions() if a.text()],
                         ['Ouvindo: diga "vai dormir" para pausar', "Parar de ouvir", "Mostrar Limitless Voice",
                          "O que eu posso dizer?", "Configurar de novo…", "Sair do Limitless Voice"])
        settings = w.findChild(SettingsDialog)
        self.assertEqual(settings.windowTitle(), "Ajustes")
        self.assertEqual(settings.model.itemText(0), "Português, rápido (instalado)")
        self.assertEqual(sorted(b.text() for b in settings.findChildren(QPushButton)), ["Cancelar", "Salvar"])
        self.assertEqual(w.findChild(CommandsDialog).windowTitle(), "O que você pode dizer")
        self.assertEqual(w.wizard.pages[3].result.text(), "✓ Ouvido: “o que eu posso dizer”. Seu microfone funciona.")
        ready = [lbl.text() for lbl in w.wizard.pages[5].findChildren(QLabel)]
        self.assertIn("<b>“ir para o compasso trinta e dois”</b> &nbsp; <span style='color:gray'>ir para qualquer "
                      "ponto</span>", ready)

    def test_changing_language_changes_the_words_in_place(self):
        self.downloaded()
        (spanish.ENGLISH_MODEL / "conf").mkdir(parents=True, exist_ok=True)
        w = self.make()
        w._show_did(w.lang.text("Listening in {language}", language="English"))   # as after a change
        w._track_focus()   # as its timer does
        english = spanish.Windows.on_screen(w)
        spanish.Windows.hub(w, "welcome", language="pt")   # Limitless Sound is in Portuguese, and so is Voice
        self.assertEqual(w.lang.code, "pt")
        self.assertEqual(spanish.Windows.on_screen(w), spanish.Windows.on_screen(self.make(language="pt")))
        spanish.Windows.hub(w, language="en")
        self.assertEqual(spanish.Windows.on_screen(w), english)

    def test_every_window_fits_in_portuguese(self):
        """Shown on a small offscreen screen, no window is larger than it, and no button, choice or
        one-line label is narrower than its words; a wrapped label is tall enough for its lines."""
        w = self.busy(self.make(language="pt"))
        w.show()
        windows = [w, w.findChild(SettingsDialog), w.findChild(CommandsDialog), w.hud]
        for window in windows:
            window.show()
        screen = QApplication.primaryScreen().availableGeometry()
        cut = []
        for page in range(len(w.wizard.pages)):
            w.wizard._show(page)
            w.wizard.show()
            QApplication.processEvents()
            cut += self.cut_off(w.wizard, f"setup page {page + 1}")
        for window in windows:
            QApplication.processEvents()
            size = window.size()
            if size.width() > screen.width() or size.height() > screen.height():
                cut.append(f"{window.windowTitle()!r} is {size.width()}x{size.height()}")
            cut += self.cut_off(window, window.windowTitle())
        self.assertEqual(cut, [])

    def test_settings_makes_room_for_the_preview_note(self):
        """Choosing Português in an open Settings shows its preview note whole, however long."""
        w = self.make()
        settings = SettingsDialog(w, w.settings)
        self.addCleanup(settings.reject)
        settings.show()
        QApplication.processEvents()
        settings.language.setCurrentIndex(settings.language.findData("pt"))
        QApplication.processEvents()
        self.assertTrue(settings.language_note.text().startswith("Prévia: em português"))
        self.assertEqual(self.cut_off(settings, "Settings"), [])
        settings.language.setCurrentIndex(settings.language.findData("en"))
        QApplication.processEvents()
        self.assertEqual(self.cut_off(settings, "Settings"), [])

    @staticmethod
    def cut_off(window, name):
        found = []
        for widget in [window, *window.findChildren(QWidget)]:
            if not widget.isVisible():
                continue
            if isinstance(widget, QLabel) and widget.wordWrap():
                if widget.heightForWidth(widget.width()) > widget.height() + 1:
                    found.append(f"{name}: {widget.text()[:60]!r} needs more height")
            elif isinstance(widget, (QLabel, QAbstractButton, QComboBox)):
                need = widget.minimumSizeHint().width() if isinstance(widget, QComboBox) else widget.sizeHint().width()
                if widget.width() + 1 < need:
                    text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                    found.append(f"{name}: {text[:60]!r} is {widget.width()} wide, needs {need}")
        return found
