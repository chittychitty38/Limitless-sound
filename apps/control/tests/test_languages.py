"""The settings page in the suite's language: every word on it has Spanish."""

import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from limitless_control import profiles
from limitless_control.suite import LANGUAGES, page_language

PAGE = Path(profiles.__file__).parent / "web" / "index.html"
TABLE = '<script type="application/json" id="strings-es">'


def _page():
    return PAGE.read_text(encoding="utf-8")


def _spanish(page):
    start = page.index(TABLE) + len(TABLE)
    return json.loads(page[start:page.index("</script>", start)].replace("<\\/", "</"))


def _script(page):
    return page[page.rindex("<script>"):]


# A sentence with bold words in it is one entry, markup and all (data-html).
_SENTENCES = re.compile(r"<(\w+)\b[^>]*\sdata-html\b[^>]*>(.*?)</\1>", re.S)


class _Text(HTMLParser):
    """The page's own words: text in the body outside scripts, aria-labels and placeholders."""

    def __init__(self):
        super().__init__()
        self.words, self.skip, self.body = [], 0, False

    def handle_starttag(self, tag, attrs):
        self.body |= tag == "body"
        self.skip += tag in ("script", "style")
        for name in ("aria-label", "placeholder", "title"):
            if self.body and dict(attrs).get(name):
                self.words.append(dict(attrs)[name])

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style")

    def handle_data(self, data):
        if self.body and not self.skip and data.strip():
            self.words.append(data.strip())


def _block(script, start):
    """The text of a constant in the page's script, from its name to the line that ends it."""
    at = script.index(start)
    return script[at:script.index("];" if start.endswith("[") else "};", at)]


# Names, controller buttons and the DAWs read the same in every language.
SAME_EVERYWHERE = {"Limitless Control", "Logic Pro", "Pro Tools", "Ableton Live", "Xbox",
                   "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS"}


def _needs_spanish(words, es):
    return [w for w in words if re.search(r"[A-Za-z]", w) and w not in es and w not in SAME_EVERYWHERE]


def test_every_word_on_the_page_has_spanish():
    page = _page()
    es = _spanish(page)
    sentences = [m.group(2).strip() for m in _SENTENCES.finditer(page)]
    assert sentences, "the welcome steps' sentences with bold words"
    parser = _Text()
    parser.feed(_SENTENCES.sub("", page))
    assert not _needs_spanish(parser.words + sentences, es), f"no Spanish for: {_needs_spanish(parser.words + sentences, es)}"


def test_every_word_the_script_shows_has_spanish():
    page = _page()
    es, script = _spanish(page), _script(page)
    said = [json.loads(f'"{m}"') for m in re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', script)]
    said += re.findall(r'\w+: "([^"]+)"', _block(script, "const INPUT_LABELS = {"))
    said += [w for pair in re.findall(r'\["\w+", "([^"]+)", [\d., ]+, "([^"]+)"\]', script) for w in pair]
    said += re.findall(r'name: "([^"]+)"', _block(script, "const PAD = ["))
    assert len(said) > 100
    assert not _needs_spanish(said, es), _needs_spanish(said, es)


def test_the_apps_own_words_have_spanish_too():
    """Profile and action names come from profiles.py: the page puts them in Spanish by their English names."""
    es = _spanish(_page())
    words = list(profiles.CATALOG) + [a["label"] for cat in profiles.CATALOG.values() for a in cat.values()]
    words += [c["label"] for c in profiles.COMMANDS.values()]
    words += [p["label"] for p in profiles.TIMING_PRESETS.values()]
    assert not _needs_spanish(words, es), _needs_spanish(words, es)


def test_spanish_keeps_every_placeholder_and_tag():
    for en, es in _spanish(_page()).items():
        assert sorted(re.findall(r"\{\w+\}", en)) == sorted(re.findall(r"\{\w+\}", es)), en
        assert Counter(re.findall(r"</?\w+>", en)) == Counter(re.findall(r"</?\w+>", es)), en


def test_the_page_has_the_languages_the_app_reports():
    page = _page()
    assert set(LANGUAGES) == {"en", *re.findall(r'id="strings-(\w+)"', page)}
    assert 'document.documentElement.lang = lang' in page   # screen readers read it in that language


def test_the_pages_language_is_the_suites_or_english():
    assert page_language({"language": "es"}) == "es"
    assert page_language({"language": "es-MX"}) == "es"
    assert page_language({"language": "EN"}) == "en"
    assert page_language({"language": "fr"}) == "en"        # one the page doesn't have yet
    assert page_language({"textScale": 1.5}) is None         # none named: the computer's
