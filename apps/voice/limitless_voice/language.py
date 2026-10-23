"""Languages: everything Voice says and listens for that isn't a keyboard shortcut.

The command packs (packs/*.yaml) are written in English and hold every shortcut and rule
(what a command presses, whether it asks first, how often it may repeat). A language is one
file, languages/<code>.yaml, with:

  models       the speech models for it; the first is the one to use
  voice        how to find a system voice for spoken replies
  words        Voice's own phrases: wake, sleep, yes, cancel, again, help, dictation...
  numbers      its number words (see numbers.py)
  keys         key names for "press ...", and letters
  sounds_like  words the speech model doesn't know, spelled as words it does
  texts        every reply and help line, keyed by its English words
  free_text_needs_both   true when "open ..." and "type ..." take their words only from the
               open recognizer (see engine.py)
  exact_destructive      true when Cut, Paste, Delete and the like run only on their exact
               words, never a near miss
  exact        true when every command runs only on its exact words: in a language whose
               short words are a letter apart ("sala" and "salva"), a near miss is another word
  commands     for each built-in pack, for each command (by its first English phrase),
               the phrases to say in this language

English is the packs' own language, so it has no texts or commands. A command's phrases
can also be given per English phrase ({stop: [parar, detener]}), so the rest of the suite,
which talks in English, hears that "parar" was a stop and not a play.
"""

import re
from functools import cache
from pathlib import Path

import yaml

from .grammar import Command, Pack, _expand_optional, compile_phrase, recognizer_phrases
from .numbers import Numbers

LANGUAGE_DIR = Path(__file__).parent / "languages"

# The phrase lists every language has under `words`.
WORD_SETS = ("wake", "sleep", "cancel", "yes", "again", "help", "dictation_on", "dictation_off",
             "take_stop", "take_off", "scratch", "new_line", "new_paragraph", "times", "twice",
             "filler_start", "filler_end", "recognize")


class Language:
    def __init__(self, data):
        self.code = data["code"]
        self.name = data["name"]                    # in the language itself: "Español"
        self.english_name = data.get("english_name", self.name)
        self.models = dict(data["models"])           # name -> {label, size}
        self.model = next(iter(self.models))
        self.voice = data.get("voice") or {}
        self.lists = {k: list(data["words"].get(k) or []) for k in WORD_SETS}
        self.words = {k: set(v) for k, v in self.lists.items()}
        self.punctuation = dict(data.get("punctuation") or {})
        self.numbers = Numbers.from_table(data["numbers"])
        keys = data.get("keys") or {}
        self.spoken_keys = dict(keys.get("names") or {})
        self.spoken_keys.update({f"f{i}": f"f{i}" for i in range(1, 21)})
        self.letters = dict(keys.get("letters") or {})
        self.f_keys = list(keys.get("f") or ["f"])
        self.sounds_like = {w: list(a) for w, a in (data.get("sounds_like") or {}).items()}
        self.texts = dict(data.get("texts") or {})
        self.commands = data.get("commands") or {}
        self.free_text_needs_both = bool(data.get("free_text_needs_both"))
        self.exact_destructive = bool(data.get("exact_destructive"))
        self.exact = bool(data.get("exact"))
        self._sounds = [(re.compile(rf"\b{re.escape(a)}\b"), w)
                        for w, aliases in self.sounds_like.items() for a in aliases]

    def __repr__(self):
        return f"<Language {self.code}>"

    @property
    def is_english(self):
        return self.code == "en"

    # -- what Voice says ---------------------------------------------------

    def text(self, english, **values):
        """A reply or help line in this language. English text is the key; the {names} in it
        are filled in after translating."""
        out = self.texts.get(english, english) if english else english
        for k, v in values.items():
            out = out.replace("{" + k + "}", str(v))
        return out

    def first(self, kind):
        """The phrase to suggest for one of Voice's own sets: "go to sleep", "a dormir"."""
        return self.lists[kind][0]

    # -- what Voice listens for ----------------------------------------------

    def builtin_phrases(self):
        """Voice's own phrases, so the recognizer knows them too."""
        sets = ("wake", "sleep", "cancel", "yes", "again", "help", "dictation_on", "dictation_off",
                "take_stop", "take_off", "recognize")
        return {w for k in sets for w in self.words[k]}

    def recognizer_phrases(self, packs):
        """Everything the command recognizer should listen for, with these packs."""
        from .actions import APP_ALIASES
        extra = self.builtin_phrases() | self.numbers.words | self.key_vocabulary() | set(APP_ALIASES)
        return recognizer_phrases(packs, extra, self)

    def key_vocabulary(self):
        """Every key name the "press ..." command understands, for the recognizer."""
        words = {p for p in list(self.spoken_keys) + list(self.letters) if not re.fullmatch(r"f\d+", p)}
        words.update(self.f_keys)   # F-keys are said "f five"
        return words

    def sounds_like_variants(self, segment):
        variants = [segment]
        for word, aliases in self.sounds_like.items():
            if re.search(rf"\b{word}\b", segment):
                variants += [re.sub(rf"\b{word}\b", a, segment) for a in aliases]
        return variants

    def undo_sounds_like(self, text):
        for pattern, word in self._sounds:
            text = pattern.sub(word, text)
        return text

    # -- the command packs, in this language -----------------------------------

    def translate(self, packs):
        """The built-in packs with this language's phrases, replies and help. Shortcuts, and
        everything else a command does, stay the English pack's."""
        if self.is_english:
            return packs
        out = []
        for pack in packs:
            mine = self.commands.get(pack.name) or {}
            out.append(Pack(pack.name, pack.apps, [self._translate(c, mine.get(c.phrases[0])) for c in pack.commands]))
        return out

    def _translate(self, cmd, spec):
        if not spec:
            return cmd   # untranslated: still there, in English, until the language file has it
        if isinstance(spec, dict):
            spoken = {eng: [spec[eng]] if isinstance(spec[eng], str) else spec[eng] for eng in spec}
        else:
            spoken = {cmd.phrases[0]: [spec] if isinstance(spec, str) else spec}
        phrases = [p for ps in spoken.values() for p in ps]
        from .engine import Engine
        fuzzy = cmd.fuzzy and not self.exact and not (self.exact_destructive and Engine._destroys(cmd, {}))
        out = Command(phrases=phrases, action=cmd.action, pack=cmd.pack, reply=self.text(cmd.reply),
                      confirm=cmd.confirm, repeatable=cmd.repeatable, help=self.text(cmd.help),
                      fuzzy=fuzzy, instant=cmd.instant, english=cmd.phrases, language=self)
        out.to_english = [(compile_phrase(p)[0], eng) for eng, ps in spoken.items() for p in ps]
        return out

    def check(self, packs=None):
        """What's wrong with this language's commands for the (English) packs, all of them on
        every computer by default: a command with no phrases here, phrases for a command that
        isn't there, a slot that doesn't match, a reply with no text. Empty when all is well."""
        problems = []
        if self.is_english:
            return problems
        packs = packs or builtin_packs()
        names = {p.name for p in packs}
        for name in self.commands:
            if name not in names:
                problems.append(f"no pack named {name!r}")
        for pack in packs:
            mine = self.commands.get(pack.name) or {}
            firsts = {c.phrases[0]: c for c in pack.commands}
            for key in mine:
                if key not in firsts:
                    problems.append(f"{pack.name}: no command {key!r}")
            for c in pack.commands:
                spec = mine.get(c.phrases[0])
                if not spec:
                    problems.append(f"{pack.name}: {c.phrases[0]!r} has no phrases in {self.code}")
                    continue
                if isinstance(spec, dict):
                    for eng in spec:
                        if eng not in c.phrases:
                            problems.append(f"{pack.name}: {c.phrases[0]!r} has no English phrase {eng!r}")
                t = self._translate(c, spec)
                want = sorted({s for _, slots in c._compiled for s in slots})
                for phrase, (_, slots) in zip(t.phrases, t._compiled):
                    if sorted(set(slots)) != want:
                        problems.append(f"{pack.name}: {phrase!r} has slots {slots}, English has {want}")
                for text in (c.reply, c.help):
                    if text and text not in self.texts:
                        problems.append(f"no {self.code} text for {text!r}")
        return problems

    def spoken_for(self, cmd, english, params):
        """How to say, in this language, what an English phrase asks of the command, with its
        slots filled in ("go to bar 32" -> "ir al compás 32"). None if it can't be said."""
        if not cmd.to_english:
            return english
        # the first phrase given for the English phrase that was meant, else the command's first
        template = next((phrase for phrase, (_, eng) in zip(cmd.phrases, cmd.to_english)
                         if compile_phrase(eng)[0].match(" " + english)), cmd.phrases[0])
        template = _expand_optional(template.lower())[0]   # without the optional words
        out = []
        for tok in template.split():
            if tok.startswith("{"):
                name, _, kind = tok[1:-1].partition(":")
                if kind == "keys" or name not in params:
                    return None
                out.append(str(params[name]))
            else:
                out.append(tok)
        return " ".join(out)


def builtin_packs():
    """The built-in packs as they are on any computer: each pack's commands for Mac and Windows."""
    from .grammar import DEFAULT_PACK_DIR, load_packs
    merged = {}
    for os_name in ("mac", "windows"):
        for pack in load_packs([DEFAULT_PACK_DIR], os_name):
            have = merged.setdefault(pack.name, Pack(pack.name, pack.apps, []))
            known = {c.phrases[0] for c in have.commands}
            have.commands += [c for c in pack.commands if c.phrases[0] not in known]
    return list(merged.values())


@cache
def load(code):
    """The language with this code ("en", "es"), or English if there's no such language."""
    path = LANGUAGE_DIR / f"{code}.yaml"
    if not path.is_file():
        path = LANGUAGE_DIR / "en.yaml"
    return Language(yaml.safe_load(path.read_text(encoding="utf-8")))


def available():
    """Every language Voice speaks: [(code, name)], English first."""
    codes = sorted(p.stem for p in LANGUAGE_DIR.glob("*.yaml"))
    return [(c, load(c).name) for c in sorted(codes, key=lambda c: (c != "en", c))]


def supported(code):
    return bool(code) and (LANGUAGE_DIR / f"{code}.yaml").is_file()


def wanted(own="", suite=None, remembered=""):
    """The language to listen and answer in: the one chosen in Voice's Settings, else Limitless
    Sound's (or the one it last sent, while the hub isn't running), else English. A language
    Voice doesn't have yet means English: "es-MX" is Spanish, "fr" is English for now."""
    for code in (own, suite, remembered):
        if code:
            code = str(code).lower().replace("_", "-").split("-")[0]
            return code if supported(code) else "en"
    return "en"


def model_for(language, chosen=""):
    """The speech model for a language: the one chosen in Settings if it's for this language,
    else the language's first."""
    return chosen if chosen in language.models else language.model


def model_language(model):
    """The language a speech model is for, or None if it isn't one Voice knows."""
    for code, _ in available():
        if model in load(code).models:
            return code
    return None


ENGLISH = load("en")
