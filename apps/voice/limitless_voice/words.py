"""Voice's windows, in the language Voice is set to.

The words come from where Voice's spoken replies come from: languages/<code>.yaml, `texts`, by
their English. So a language is still one file, words that are both shown and said are
translated once, and English needs nothing: it's written in the code. Text with no translation
in a language stays English. The windows ask for their words the way the rest of Voice asks a
language for its replies, ui.text("Settings"), so tests/test_language.py finds them all too.

The language is the one chosen in Settings › Language, else Limitless Sound's (language.wanted).
The windows change to it at once, even while its speech model is still to be downloaded. The
words they suggest saying ("what can I say", "qué puedo decir") are the ones Voice listens for,
so they're in the language it listens in (phrase()), which changes once the model is here.

Words on screen are set with show(), or kept by the label that shows them (look.LiveText), so
that when either language changes show_again() puts each one in the new language, in place: the
keyboard focus and what a screen reader is on stay put.
"""

import weakref

from .language import ENGLISH, load

_language = ENGLISH    # the windows'
_listening = ENGLISH   # the one Voice listens in


def language():
    """The language Voice's windows are in (a language.Language)."""
    return _language


def use(code):
    """Show Voice's windows in this language ("es") from now on. True when that changes it."""
    global _language
    before, _language = _language, load(code)
    return _language.code != before.code


def listen_in(language):
    """Voice listens in this language (a language.Language) from now on: what the windows suggest
    saying is in it."""
    global _listening
    _listening = language


# ---- words --------------------------------------------------------------------------

class Text(str):
    """Words in one language that remember their English, so again() can say them in another."""
    english = ""
    values = {}


class Shown:
    """The language Voice's windows are in, asked for words like any language: ui.text("Settings")
    is "Ajustes" when they're in Spanish."""

    def text(self, english, /, **values):
        """The words in the windows' language, with each {name} filled in from values."""
        said = Text(_language.text(english, **values))
        said.english, said.values = english, values
        return said


ui = Shown()


class Phrase(Text):
    """Words to say to Voice, in the language it listens in."""


def phrase(english):
    """Words to say to Voice, shown as an example: in the language it listens in, from the same
    table. "go to bar thirty two" is "ir al compás treinta y dos"."""
    said = Phrase(_listening.text(english))
    said.english = english
    return said


def again(text):
    """The same words in the language in use now. Text that didn't come from ui.text() or
    phrase() stays as it is: a device's name, what was heard, a reply."""
    if isinstance(text, Phrase):
        return phrase(text.english)
    if isinstance(text, Text):
        return ui.text(text.english, **{k: again(v) for k, v in text.values.items()})
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
    """Put every word on screen in the languages in use now. Words that read the same in both
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
