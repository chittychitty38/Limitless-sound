"""The suite's language: one choice every app follows, and replies read by a voice for it."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from test_bus import TOKEN, FakeLauncher, FakeSpeaker, bus, connect  # noqa: F401 (bus is a fixture)

from limitless_hub import catalog, languages, setup, speech
from limitless_hub.bus import Bus


def test_a_language_is_its_primary_tag_and_only_one_the_suite_has():
    assert languages.tag("es") == "es"
    assert languages.tag("es-MX") == "es"
    assert languages.tag("es_ES.UTF-8") == "es"
    assert languages.tag("EN-us") == "en"
    assert languages.tag("fr-FR") is None
    assert languages.tag(None) is None
    assert languages.tag(3) is None


def test_the_computers_language_is_the_first_one_the_suite_has():
    assert languages.system_language(lambda: ["es-MX", "en-US"]) == "es"
    assert languages.system_language(lambda: ["fr-FR", "es-ES"]) == "es"
    assert languages.system_language(lambda: ["fr-FR", "de-DE"]) == "en"
    assert languages.system_language(lambda: []) == "en"

    def broken():
        raise OSError("no defaults")

    assert languages.system_language(broken) == "en"


def test_first_start_takes_the_computers_language_and_a_choice_is_kept(monkeypatch):
    monkeypatch.setattr(languages, "system_language", lambda: "es")
    assert Bus({}, TOKEN).settings["prefs"]["language"] == "es"
    assert Bus({"prefs": {"language": "en"}}, TOKEN).settings["prefs"]["language"] == "en"


def test_language_takes_only_languages_the_suite_has(bus):  # noqa: F811
    assert bus.set_prefs({"language": "es-MX"})["language"] == "es"
    assert bus.set_prefs({"language": "fr"})["language"] == "es"
    assert bus.set_prefs({"language": 5})["language"] == "es"
    assert bus.set_prefs({"language": "en"})["language"] == "en"


def test_every_app_hears_the_language(bus):  # noqa: F811
    _, inbox = connect(bus, "voice")
    bus.set_prefs({"language": "es"})
    assert [m["prefs"]["language"] for m in inbox if m["op"] == "prefs"] == ["es"]


def test_text_is_read_in_the_language_its_app_follows():
    b = Bus({"prefs": {"language": "es"}}, TOKEN, speaker=FakeSpeaker(), launcher=FakeLauncher())
    voice, _ = connect(b, "voice")
    zoom, _ = connect(b, "zoom")
    b.receive(voice, {"op": "state", "key": "prefs.applied", "value": {"language": "es", "textScale": 1.0}})
    b.receive(voice, {"op": "say", "text": "Grabando"})
    b.receive(zoom, {"op": "say", "text": "Zoomed in"})          # Zoom doesn't report a language yet
    b.receive(zoom, {"op": "say", "text": "Ampliado", "lang": "es"})
    b.invoke("hub.say", {"text": "Hola", "lang": "es-MX"})
    b.invoke("hub.say", {"text": "Hello"})
    assert list(zip(b.speaker.said, b.speaker.langs)) == [
        ("Grabando", "es"), ("Zoomed in", "en"), ("Ampliado", "es"), ("Hola", "es"), ("Hello", "en")]


def test_the_page_says_when_the_computer_has_no_voice_for_the_language():
    class NoSpanish(FakeSpeaker):
        def has_voice(self, lang):
            return lang != "es"

    b = Bus({"prefs": {"language": "en"}}, TOKEN, speaker=NoSpanish(), launcher=FakeLauncher())
    snap = b.snapshot()
    assert snap["languageVoice"] is True and snap["languages"] == languages.LANGUAGES
    b.set_prefs({"language": "es"})
    assert b.snapshot()["languageVoice"] is False


def test_the_guided_setup_carries_the_language():
    assert setup.plan(["voice"], {"language": "es"})["prefs"]["language"] == "es"
    assert "language" not in setup.plan(["voice"], {"language": "klingon"})["prefs"]
    assert "language" not in setup.plan(["voice"], {})["prefs"]


VOICES = [("Albert", "en_US"), ("Eddy (Spanish (Spain))", "es_ES"), ("Paulina", "es_MX"),
          ("Amélie", "fr_CA"), ("Microsoft Sabina Desktop", "es-MX")]


def test_a_voice_for_the_language_clearer_ones_first():
    assert speech.voice_for("es", VOICES) == "Paulina"
    assert speech.voice_for("es", [("Eddy (Spanish (Spain))", "es_ES")]) == "Eddy (Spanish (Spain))"
    assert speech.voice_for("es", [("Microsoft Sabina Desktop", "es-MX")]) == "Microsoft Sabina Desktop"
    assert speech.voice_for("es", [("Albert", "en_US")]) is None


def test_the_speaker_reads_each_language_with_its_voice_and_looks_again_for_a_new_one():
    clock = [0.0]
    lists = [[("Albert", "en_US")], VOICES]
    spoken = []
    s = speech.Speaker(runner=lambda text, lang: spoken.append((text, lang)), clock=lambda: clock[0],
                       list_voices=lambda: lists.pop(0) if len(lists) > 1 else lists[0])
    assert s.voice("en") is None                 # English keeps the computer's own voice
    assert s.voice("es") is None
    clock[0] += 5
    assert s.voice("es") is None                 # not listed again straight away
    clock[0] += speech.RELIST_AFTER
    assert s.voice("es") == "Paulina"            # a voice added in the computer's settings is found
    assert s.say("Grabando", lang="es")


def test_the_commands_that_speak_another_language():
    import sys

    cmd = speech._command("Grabando", "es", "Paulina")
    if sys.platform == "darwin":
        assert cmd == ["say", "-v", "Paulina", "Grabando"]
    elif sys.platform.startswith("win"):
        assert "SelectVoice('Paulina')" in cmd[-1] and "Speak('Grabando')" in cmd[-1]
    elif cmd:
        assert "es" in cmd and cmd[-1] == "Grabando"
    if sys.platform.startswith("win"):
        assert "SelectVoice" not in speech._command("It's on")[-1]
        assert "Speak('It''s on')" in speech._command("It's on")[-1]


def test_the_page_offers_every_language_in_its_own_name():
    page = (Path(languages.__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
    for code, name in languages.LANGUAGES.items():
        assert page.count(f'<option value="{code}" lang="{code}">{name}</option>') == 2  # setup and settings


def _page():
    return (Path(languages.__file__).parent / "web" / "index.html").read_text(encoding="utf-8")


def _spanish(page):
    start = page.index('<script type="application/json" id="strings-es">') + len('<script type="application/json" id="strings-es">')
    return json.loads(page[start:page.index("</script>", start)].replace("<\\/", "</"))


class _Text(HTMLParser):
    """The page's own words: text in the body outside scripts, and aria-labels."""

    def __init__(self):
        super().__init__()
        self.words, self.skip, self.body = [], 0, False

    def handle_starttag(self, tag, attrs):
        self.body |= tag == "body"
        self.skip += tag in ("script", "style")
        if self.body and dict(attrs).get("aria-label"):
            self.words.append(dict(attrs)["aria-label"])

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style")

    def handle_data(self, data):
        if self.body and not self.skip and data.strip():
            self.words.append(data.strip())


# Names and the language picker read the same in every language.
SAME_EVERYWHERE = {"Limitless Sound", "Language ·", "Idioma", *languages.LANGUAGES.values()}


def test_every_word_on_the_page_has_spanish():
    page = _page()
    es = _spanish(page)
    parser = _Text()
    parser.feed(page)
    missing = [w for w in parser.words if w not in es and w not in SAME_EVERYWHERE]
    assert not missing, f"no Spanish for: {missing}"
    script = page[page.rindex("<script>"):]
    said = [json.loads(f'"{m}"') for m in re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', script)]
    said += re.findall(r'\["[\w.]+(?:=\w+)?", "([^"]+)"\]', script)  # the link events
    assert said and not [s for s in said if s not in es], [s for s in said if s not in es]


def test_the_hubs_own_words_have_spanish_too():
    es = _spanish(_page())
    words = [w for c in setup.choices() for w in (c["label"], c["about"])]
    words += [spec["about"] for spec in catalog.TOOLS.values()]
    assert not [w for w in words if w not in es], [w for w in words if w not in es]


def test_spanish_keeps_every_placeholder():
    for en, es in _spanish(_page()).items():
        assert sorted(re.findall(r"\{\w+\}", en)) == sorted(re.findall(r"\{\w+\}", es)), en


def test_a_speaker_that_takes_only_the_text_still_speaks_english():
    class TextOnly:
        def __init__(self):
            self.said = []

        def say(self, text):
            self.said.append(text)

    b = Bus({"prefs": {"language": "en"}}, TOKEN, speaker=TextOnly(), launcher=FakeLauncher())
    b.invoke("hub.status")
    b.invoke("hub.say", {"text": "Hello"})
    assert b.speaker.said[-1] == "Hello" and len(b.speaker.said) == 2
