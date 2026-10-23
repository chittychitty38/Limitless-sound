"""Command packs: load them from YAML and match spoken phrases against them.

A phrase template is plain words plus two extras:
  [word]          an optional word ("open [the] mixer")
  {name:type}     a slot; type is number, word, text or keys

Example: "go to bar {bar:number}" matches "go to bar 32" with bar=32.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .keys import KeyChordError, spoken_to_chord

SLOT_PATTERNS = {
    "number": r"\d+",
    "word": r"\S+",
    "text": r".+?",
    "keys": r".+?",
}


def _convert(kind, raw, language=None):
    if kind == "number":
        return int(raw)
    if kind == "keys":
        return spoken_to_chord(raw, language)
    return raw


@dataclass
class Command:
    phrases: list
    action: dict
    pack: str
    reply: str = ""
    confirm: bool = False
    repeatable: object = True    # True, False, or the most times one utterance may run it
    help: str = ""
    fuzzy: bool = True
    instant: bool = False       # run the moment it's heard, before the utterance is over
    english: list = None        # the pack's own phrases, when these are another language's
    language: object = None     # the language the phrases are in (None: English)
    to_english: list = field(default_factory=list, repr=False)   # [(phrase regex, English phrase)]
    _compiled: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compiled = [compile_phrase(p) for p in self.phrases]
        if self.english is None:
            self.english = list(self.phrases)
        self._english = self._compiled if self.english == self.phrases else None

    @property
    def literal_phrases(self):
        """Phrases with no slots, expanded for optional words. Used for fuzzy matching."""
        out = []
        for p in self.phrases:
            if "{" not in p:
                out.extend(_expand_optional(p))
        return out

    @property
    def free_text(self):
        """Whether a phrase has a {text} slot, which takes any words at all."""
        return any(kind == "text" for _, slots in self._compiled for _, kind in slots)

    def match(self, text):
        return _match(self._compiled, text, self.language)

    def match_english(self, text):
        """match(), for the pack's own English phrases: what the rest of the suite sends."""
        if self._english is None:
            self._english = [compile_phrase(p) for p in self.english]
        return _match(self._english, text, None)

    def english_of(self, text):
        """The English phrase that words said in this command's language stand for, so the rest
        of the suite hears which intent it was ("parar" -> "stop"). None if it's unclear."""
        if not self.to_english:
            return text
        return next((eng for regex, eng in self.to_english if regex.match(" " + text)), None)


def _match(compiled, text, language):
    for regex, slots in compiled:
        m = regex.match(" " + text)
        if not m:
            continue
        try:
            params = {name: _convert(kind, m.group(name), language) for name, kind in slots}
        except KeyChordError:
            continue
        return params
    return None


def _expand_optional(phrase):
    m = re.search(r"\[([^\]]+)\]", phrase)
    if not m:
        return [" ".join(phrase.split())]
    without = phrase[:m.start()] + phrase[m.end():]
    with_ = phrase[:m.start()] + m.group(1) + phrase[m.end():]
    return _expand_optional(without) + _expand_optional(with_)


def compile_phrase(phrase):
    slots = []
    parts = []
    for tok in phrase.lower().split():
        if tok.startswith("{") and tok.endswith("}"):
            name, _, kind = tok[1:-1].partition(":")
            kind = kind or "word"
            if kind not in SLOT_PATTERNS:
                raise ValueError(f"unknown slot type {kind!r} in {phrase!r}")
            slots.append((name, kind))
            parts.append((f"(?P<{name}>{SLOT_PATTERNS[kind]})", False))
        elif tok.startswith("[") and tok.endswith("]"):
            parts.append((re.escape(tok[1:-1]), True))
        else:
            parts.append((re.escape(tok), False))
    # Every word carries its leading space, so an optional first word works;
    # match() prepends a space to the text to line up.
    regex = "".join(f"(?:\\s+{pat})?" if optional else f"\\s+{pat}" for pat, optional in parts)
    return re.compile(f"^{regex}$"), slots


@dataclass
class Pack:
    name: str
    apps: list
    commands: list

    @property
    def is_global(self):
        return not self.apps

    def applies_to(self, app):
        if self.is_global:
            return True
        key = _app_key(app)
        return bool(key) and any(key.startswith(_app_key(a)) for a in self.apps)


def _app_key(name):
    """"Pro Tools", "ProTools.exe" and "pro tools" all compare equal."""
    name = (name or "").lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return "".join(ch for ch in name if ch.isalnum())


def _literal(action):
    if "steps" in action:
        return {**action, "steps": [_literal(a) for a in action["steps"]]}
    return {**action, "literal": True} if "keys" in action else action


def _on(platforms, os_name):
    return not platforms or os_name in platforms


def load_pack(path, os_name="mac"):
    """Load a pack, keeping only what applies to os_name ("mac" or "windows").

    A pack or a command can say `platforms: [mac]`, and a command can give
    `do_mac:` or `do_windows:` to replace `do:` on that platform.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    name = data.get("name") or Path(path).stem
    if not _on(data.get("platforms"), os_name):
        return None
    commands = []
    for entry in data.get("commands", []):
        if not _on(entry.get("platforms"), os_name):
            continue
        if f"do_{os_name}" in entry:
            # a platform's own action is written in that platform's key names
            action = _literal(entry[f"do_{os_name}"])
        else:
            action = entry.get("do")
        if action is None:
            continue
        phrases = entry["say"]
        if isinstance(phrases, str):
            phrases = [phrases]
        commands.append(Command(
            phrases=phrases,
            action=action,
            pack=name,
            reply=entry.get("reply", ""),
            confirm=bool(entry.get("confirm", False)),
            repeatable=entry.get("repeatable", True),
            help=entry.get("help", ""),
            fuzzy=entry.get("fuzzy", not entry.get("confirm", False)),
            instant=bool(entry.get("instant", False)),
        ))
    return Pack(name=name, apps=data.get("apps") or [], commands=commands)


def load_packs(dirs, os_name="mac"):
    packs = []
    for d in dirs:
        if not Path(d).is_dir():
            continue
        for path in sorted(Path(d).glob("*.y*ml")):
            pack = load_pack(path, os_name)
            if pack:
                packs.append(pack)
    return packs


def vocabulary(packs):
    """Every literal word in every phrase."""
    words = set()
    for pack in packs:
        for cmd in pack.commands:
            for phrase in cmd.phrases:
                for tok in phrase.lower().split():
                    if not tok.startswith("{"):
                        words.add(tok.strip("[]"))
    return words


def recognizer_phrases(packs, extra=(), language=None):
    """What the command recognizer listens for: every fixed run of words in
    every phrase ("go to bar", "show the mixer"), plus extra words and phrases.

    Whole phrases work much better than loose words: the recognizer can't
    stitch together nonsense like "delta bar" from a list of single words.
    Words the speech model doesn't know are spelled as words it does (the
    language's sounds_like); normalize() turns them back.
    """
    if language is None:
        from .language import ENGLISH as language
    units = set()
    for pack in packs:
        for cmd in pack.commands:
            for phrase in cmd.phrases:
                for expanded in _expand_optional(phrase.lower()):
                    for segment in re.split(r"\{[^}]+\}", expanded):
                        segment = " ".join(segment.split())
                        if segment:
                            units.update(language.sounds_like_variants(segment))
    for e in extra:
        units.update(language.sounds_like_variants(e))
    return units


def undo_sounds_like(text, language=None):
    if language is None:
        from .language import ENGLISH as language
    return language.undo_sounds_like(text)


DEFAULT_PACK_DIR = Path(__file__).parent / "packs"
