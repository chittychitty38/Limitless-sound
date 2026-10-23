"""Voice commands in Spanish: what Zoom listens for and how it judges what it hears, which language
it listens in (the suite's, or one chosen for voice), and the Spanish speech model: found where
Limitless Voice keeps it, else downloaded once while Zoom keeps listening in English and says so."""

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from limitless_zoom import app as app_module  # noqa: E402
from limitless_zoom import settings as settings_module  # noqa: E402
from limitless_zoom import voice, words  # noqa: E402
from limitless_zoom.actions import LABELS, SPANISH_PHRASES, VOICE_PHRASES  # noqa: E402
from limitless_zoom.app import ZoomApp  # noqa: E402
from limitless_zoom.settings import Settings, voice_app_models  # noqa: E402
from limitless_zoom.voice import ENGLISH, LANGUAGES, SPANISH  # noqa: E402
from test_ui import PermBackend  # noqa: E402


def w(word, start, end, conf=1.0):
    return {"word": word, "start": start, "end": end, "conf": conf}


# ---- what Zoom listens for in Spanish ------------------------------------------------------

def test_every_spoken_action_can_be_said_in_spanish():
    assert set(SPANISH_PHRASES.values()) <= set(LABELS)
    assert set(SPANISH_PHRASES.values()) == set(VOICE_PHRASES.values())
    assert LANGUAGES == {"en": ENGLISH, "es": SPANISH}
    assert SPANISH.model == "vosk-model-small-es-0.42" and SPANISH.url.endswith("/vosk-model-small-es-0.42.zip")


def test_spanish_phrases_are_plain_words_the_recognizer_can_take():
    for phrase in SPANISH_PHRASES:
        assert phrase == phrase.lower().strip() and "  " not in phrase, phrase
        assert all(c.isalpha() or c == " " for c in phrase), phrase
        # A filler is dropped from what's heard, so it can't be part of a command.
        assert voice.without(phrase.split(), SPANISH.fillers) == phrase.split(), phrase
    vocab = json.loads(SPANISH.grammar())
    assert "acercar" in vocab and "por favor" in vocab and vocab[-1] == "[unk]"
    assert "zoom in" not in vocab and "acercar" not in json.loads(ENGLISH.grammar())
    assert "más altas" in SPANISH.grammar()   # written as itself, not as \u escapes


def test_spanish_commands_are_matched_like_english_ones():
    words_ = [{"word": "acercar", "conf": 0.9}]
    assert SPANISH.match("acercar", words_, 0.5) == "in"
    assert SPANISH.match("alejar", [], 0.5) == "out"
    assert SPANISH.match("más altas", [], 0.5) == "taller"
    assert SPANISH.match("otra vez", [], 0.5) == "again"
    assert SPANISH.match("acercar", [{"word": "acercar", "conf": 0.3}], 0.5) is None   # not sure
    assert SPANISH.match("zoom in", [], 0.5) is None       # English, heard while listening in Spanish
    assert ENGLISH.match("acercar", [], 0.5) is None
    assert voice.match_phrase("acercar", [], 0.5, SPANISH) == "in"
    assert voice.match_phrase("zoom in", [], 0.5) == "in"  # English when no language is given


def test_the_sentence_rules_hold_in_spanish():
    # "[unk]" around it is a breath or a click; two together, or words running on, a sentence.
    assert SPANISH.match("[unk] acercar [unk]", [], 0.5) == "in"
    assert SPANISH.match("[unk] [unk] reducir", [], 0.5) is None
    assert SPANISH.match("[unk] alejar", [w("[unk]", 0.0, 0.40), w("alejar", 0.42, 0.9)], 0.5) is None
    assert SPANISH.match("[unk] alejar", [w("[unk]", 0.0, 0.20), w("alejar", 0.60, 1.0)], 0.5) == "out"
    assert SPANISH.match("ajustar [unk]", [w("ajustar", 0, .5), w("[unk]", .52, .9)], 0.5) is None


def test_por_favor_and_gracias_around_a_spanish_command_are_fine():
    heard = [w("acercar", 0, .5), w("por", .52, .7), w("favor", .7, .95)]
    assert SPANISH.match("acercar por favor", heard, 0.5) == "in"
    assert SPANISH.match("gracias", [w("gracias", 0, .4)], 0.5) is None
    assert SPANISH.match("por favor", [], 0.5) is None
    assert SPANISH.match("ajustar please", [], 0.5) is None   # English fillers are English's
    # "por" alone is a word like any other ("por acercar"): only "por favor" together is ignored.
    assert SPANISH.match("por acercar", [w("por", 0, .2), w("acercar", .6, 1)], 0.5) is None
    assert voice.without(["favor", "por", "acercar", "por", "favor"], SPANISH.fillers) == ["favor", "por", "acercar"]
    assert SPANISH.confidence([w("acercar", 0, .5, 0.6), w("por", .5, .6, 0.2), w("favor", .6, .8, 0.2)]) == 0.6


def test_common_spanish_words_are_written_down_and_do_nothing():
    # The Spanish model writes talk down as the nearest command unless it has other words to
    # choose: common_words.py. Said alone they do nothing; around a command, it isn't one.
    assert len(SPANISH.others) > 300 and not ENGLISH.others
    assert {"de", "la", "y", "que", "para"} <= set(SPANISH.others) <= SPANISH.words()
    assert "de" in json.loads(SPANISH.grammar())
    assert SPANISH.match("para", [w("para", 0, .3)], 0.5) is None
    assert SPANISH.match("para reducir", [w("para", 0, .3), w("reducir", .8, 1.3)], 0.5) is None
    assert SPANISH.match("reducir el", [w("reducir", 0, .4), w("el", .9, 1.0)], 0.5) is None
    assert SPANISH.match("más altas", [w("más", 0, .3), w("altas", .3, .7)], 0.5) == "taller"   # "más" is one too
    # Not a word that sounds like a one-word command: it would take the commands people say.
    single = [p for p in SPANISH.phrases if " " not in p]
    assert not [o for o in SPANISH.others for c in single if o != c and (o in c or c in o) and abs(len(o) - len(c)) <= 2]


def test_what_to_say_first_and_by_action():
    assert ENGLISH.first("in") == "zoom in" and SPANISH.first("in") == "acercar"
    assert SPANISH.by_action()["out"][:2] == ["alejar", "reducir"]
    assert SPANISH.first("sideways") is None
    more = SPANISH.adding({"acerca": "in"})
    assert more.match("acerca", [], 0.5) == "in" and SPANISH.match("acerca", [], 0.5) is None


# ---- the speech models ---------------------------------------------------------------------

def model(folder):
    (folder / "am").mkdir(parents=True)
    return folder


def test_each_language_finds_its_own_model(tmp_path):
    zoom, voice_app = tmp_path / "zoom", tmp_path / "voice"
    model(zoom / ENGLISH.model)
    assert voice.find_model(None, [zoom, voice_app], SPANISH) is None
    model(voice_app / SPANISH.model)   # Limitless Voice downloaded it
    assert voice.find_model(None, [zoom, voice_app], SPANISH) == voice_app / SPANISH.model
    assert voice.find_model(None, [zoom, voice_app]) == zoom / ENGLISH.model
    # A model chosen in the settings is for the language its name says; one that doesn't say is English.
    big = model(tmp_path / "vosk-model-es-0.42")
    mine = model(tmp_path / "my model")
    assert voice.find_model(str(big), [zoom], SPANISH) == big and voice.find_model(str(big), [zoom]) == zoom / ENGLISH.model
    assert voice.find_model(str(mine), [zoom]) == mine and voice.find_model(str(mine), [], SPANISH) is None
    assert voice.model_language("vosk-model-small-en-us-0.15") == "en" and voice.model_language("x") is None


def test_limitless_voices_model_folder_on_each_computer(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "os_name", lambda: "mac")
    assert voice_app_models() == Path.home() / "Library" / "Application Support" / "Limitless Voice" / "models"
    monkeypatch.setattr(settings_module, "os_name", lambda: "win")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert voice_app_models() == tmp_path / "Limitless Voice" / "models"
    monkeypatch.setattr(settings_module, "os_name", lambda: "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert voice_app_models() == tmp_path / "share" / "Limitless Voice" / "models"
    monkeypatch.setenv("XDG_DATA_HOME", "")
    assert voice_app_models() == Path.home() / ".local" / "share" / "Limitless Voice" / "models"


def zipped(tmp_path, name, good=True):
    """A model's zip file, at a file:// URL."""
    path = tmp_path / f"{name}.zip"
    if good:
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(f"{name}/am/final.mdl", b"model")
            z.writestr(f"{name}/conf/model.conf", b"conf")
    else:
        path.write_bytes(b"not a zip")
    return path.as_uri()


def test_a_model_is_downloaded_whole_or_not_at_all(tmp_path, monkeypatch):
    lang = SPANISH.adding({})
    lang.url = zipped(tmp_path, lang.model)
    got = voice.download_model(tmp_path / "models", language=lang)
    assert got == tmp_path / "models" / lang.model and (got / "am" / "final.mdl").read_bytes() == b"model"
    assert [p.name for p in (tmp_path / "models").iterdir()] == [lang.model]   # nothing left over
    lang.url = zipped(tmp_path, lang.model, good=False)
    with pytest.raises(zipfile.BadZipFile):
        voice.download_model(tmp_path / "other", language=lang)
    assert list((tmp_path / "other").iterdir()) == []   # never half a model to be taken for one


# ---- which language Zoom listens in ------------------------------------------------------------

class Listener:
    """Stands in for VoiceListener: no microphone, no model."""

    def __init__(self, model_path, on_action, on_status, device=None, min_conf=0.55, on_heard=None,
                 on_level=None, language=ENGLISH):
        self.model_path, self.on_status, self.language = model_path, on_status, language
        self.asleep = self.stopped = False

    def start(self):
        self.on_status(words.t("Listening on {name}", name="Fake Mic"))

    def stop(self):
        self.stopped = True


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Zoom's model folder and Limitless Voice's, empty; downloads come from file:// URLs."""
    zoom, voice_app = tmp_path / "zoom", tmp_path / "voice"
    monkeypatch.setattr(app_module, "model_dirs", lambda: [zoom / "models", voice_app])
    monkeypatch.setattr(app_module, "config_dir", lambda: zoom)
    for lang in LANGUAGES.values():   # never the internet: a download fails at once unless a test says
        monkeypatch.setattr(lang, "url", (tmp_path / "nowhere.zip").as_uri())
    monkeypatch.setattr(voice, "VoiceListener", Listener)
    monkeypatch.setattr(voice, "list_microphones", lambda: [])   # names would leak in
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    return zoom / "models", voice_app


@pytest.fixture
def make(qapp, tmp_path, folders, monkeypatch):
    made = []

    def make(settings=None, setup=False):
        s = Settings(tmp_path / f"settings{len(made)}.json")
        s.update({"speak": False, "first_run": setup, **(settings or {})})
        app = ZoomApp(s, PermBackend(), use_keys=False, use_voice=True, use_tray=True)
        app.sent = []
        app.suite.link._send = lambda msg: app.sent.append(msg) or True   # no hub
        app.said = []
        app.toast.show_text = lambda text, *a, **k: app.said.append(text)
        app.start()
        made.append(app)
        return app

    yield make
    for app in made:
        app.stop_voice()
        for win in (app.setup_window, app.panel, app.toast, app.badge, app.tray):
            if win is not None:
                win.hide()
        app.poll.stop()
        app.perm_timer.stop()
        app.server.close()


def wait_for(cond, ms=3000):
    for _ in range(ms // 20):
        if cond():
            return True
        QTest.qWait(20)
    return bool(cond())


def hub(app, **prefs):
    app.suite.link._handle({"op": "prefs", "prefs": prefs})


def test_listens_in_the_suites_language_with_voices_model(make, folders):
    zoom, voice_app = folders
    model(zoom / ENGLISH.model)
    model(voice_app / SPANISH.model)
    app = make()
    assert app.voice.language is ENGLISH and app.voice.model_path == str(zoom / ENGLISH.model)
    hub(app, language="es")   # Limitless Sound is in Spanish
    assert app.voice.language is SPANISH and app.voice.model_path == str(voice_app / SPANISH.model)
    assert app._downloading == set()   # Voice's model, never downloaded again
    hub(app, language="en")
    assert app.voice.language is ENGLISH


def test_a_language_chosen_for_voice_wins_over_the_suites(make, folders, monkeypatch):
    zoom, voice_app = folders
    model(zoom / ENGLISH.model)
    model(zoom / SPANISH.model)
    monkeypatch.setattr(words, "_computer", "es")
    app = make({"voice_language": "en"})
    assert words.language() == "es" and app.voice.language is ENGLISH   # windows in Spanish, commands in English
    app.set_voice_language("es-MX")
    assert app.voice.language is SPANISH and app.settings["voice_language"] == "es-MX"
    app.set_voice_language(None)   # the windows' language again
    assert app.voice.language is SPANISH
    hub(app, language="en")
    assert app.voice.language is ENGLISH
    assert Settings(app.settings.path)["voice_language"] is None   # saved


def test_the_menu_chooses_the_language_for_voice(make, folders):
    model(folders[0] / ENGLISH.model)
    model(folders[0] / SPANISH.model)
    app = make()
    hub(app, language="es")
    menu = app.language_menu   # not QAction.menu(): PySide deletes the menu with what it returns
    assert menu.title() == "Idioma de los comandos de voz"
    menu.aboutToShow.emit()
    items = menu.actions()
    assert [a.text() for a in items] == ["Igual que Limitless Sound (español)", "English", "Español"]
    assert [a.isChecked() for a in items] == [True, False, False]
    items[1].trigger()
    assert app.settings["voice_language"] == "en" and app.voice.language is ENGLISH
    menu.aboutToShow.emit()
    assert [a.isChecked() for a in menu.actions()] == [False, True, False]


def test_spanish_is_downloaded_once_while_english_keeps_listening(make, folders, monkeypatch, tmp_path):
    zoom, voice_app = folders
    model(zoom / ENGLISH.model)
    url = zipped(tmp_path, SPANISH.model)
    monkeypatch.setattr(SPANISH, "url", url)
    statuses = []
    monkeypatch.setattr(words, "_computer", "es")
    app = make()
    app.bus.voice_status.connect(statuses.append)
    app.start_voice()
    assert app.voice.language is ENGLISH   # until it's here
    assert statuses[-1] == ("Escuchando en Fake Mic; hasta que se descargue el modelo de voz en español "
                            "(39 MB, solo esta vez), di los comandos en inglés")
    assert wait_for(lambda: app.voice.language is SPANISH)
    assert app.voice.model_path == str(zoom / SPANISH.model)
    assert statuses[-1] == "Escuchando en Fake Mic"
    assert app.said[-1] == "Comandos de voz en español"
    app.start_voice()
    assert app._downloading == set()   # here now: never downloaded again


def test_a_failed_download_says_why_and_keeps_english(make, folders, monkeypatch, tmp_path):
    model(folders[0] / ENGLISH.model)
    monkeypatch.setattr(SPANISH, "url", zipped(tmp_path, SPANISH.model, good=False))
    app = make()
    shown = []
    app.bus.voice_status.connect(shown.append)
    hub(app, language="es")
    assert wait_for(lambda: not app._downloading)
    assert wait_for(lambda: "no se pudo descargar el modelo de voz en español" in app.panel.voice_label.text())
    assert app.voice.language is ENGLISH and "di los comandos en inglés" in shown[-1]
    hub(app, language="en")
    assert app.panel.voice_label.text() == "Voice: Listening on Fake Mic"   # back to English, nothing to say


def test_with_no_model_at_all_spanish_is_downloaded_first(make, folders, monkeypatch, tmp_path):
    monkeypatch.setattr(SPANISH, "url", zipped(tmp_path, SPANISH.model))
    monkeypatch.setattr(words, "_computer", "es")
    app = make()
    assert app.panel.voice_label.text() in ("Voz: descargando el modelo de voz en español (unos 39 MB), solo esta vez…",
                                            "Voz: Escuchando en Fake Mic")
    assert wait_for(lambda: app.voice is not None and app.voice.language is SPANISH)
    assert app.said == [] or app.said[-1] != "Comandos de voz en español"   # nothing was heard in English meanwhile


def test_a_download_no_longer_wanted_is_kept_but_not_used(make, folders, monkeypatch, tmp_path):
    model(folders[0] / ENGLISH.model)
    monkeypatch.setattr(SPANISH, "url", zipped(tmp_path, SPANISH.model))
    app = make()
    app._voice_ready(str(folders[0] / SPANISH.model), "es")   # English is wanted
    assert app.voice.language is ENGLISH


# ---- what can be said ----------------------------------------------------------------------------

def test_setup_lists_what_can_be_said_in_the_language_voice_works_in(make, folders, monkeypatch):
    model(folders[0] / ENGLISH.model)
    model(folders[0] / SPANISH.model)
    app = make(setup=True)
    assert wait_for(lambda: app.setup_window is not None)
    setup = app.setup_window
    assert "<b>Zoom in</b>: “zoom in”, “closer”" in setup.phrases.text()
    assert setup.heard.text() == "Say “zoom in” to try it."
    hub(app, language="es")
    assert "<b>Acercar</b>: «acercar», «ampliar»" in setup.phrases.text()
    assert "<b>Pistas más altas</b>: «más altas», «pistas más altas»" in setup.phrases.text()
    assert setup.heard.text() == "Di «acercar» para probarlo."
    app.set_voice_language("en")   # windows in Spanish, commands in English
    assert "<b>Acercar</b>: «zoom in», «closer»" in setup.phrases.text()
    assert setup.heard.text() == "Di «zoom in» para probarlo."
    app._heard("acercar")
    hub(app, language="en")
    assert setup.heard.text() == "Heard: “acercar”"   # what was heard stays
    app._setup_done()
    assert app.said[-1].startswith("Ready. Say zoom in, or tap")


def test_the_suite_still_gets_the_english_phrases(make, folders, monkeypatch):
    # Limitless Voice adds other apps' phrases only when it listens in English.
    app = make()
    hub(app, language="es")
    acts = {a["id"]: a for a in app.suite.link._actions}
    assert "zoom in" in acts["in"]["phrases"]
