"""The voice command engine: takes recognized text, decides what to do.

It knows three states:
  asleep     ignores everything except a wake phrase, so talking to a
             bandmate or singing a take never triggers anything
  command    matches phrases against the packs for the app in front
  dictation  types what you say into the focused field
"""

import difflib
import re
from dataclasses import dataclass, field

from .actions import run_action
from .grammar import undo_sounds_like
from .numbers import normalize_numbers

WAKE = {"wake up", "start listening", "computer wake up"}
SLEEP = {"go to sleep", "stop listening"}
CANCEL = {"cancel", "never mind", "nevermind", "no"}
YES = {"yes", "confirm", "do it", "yes please"}
AGAIN = {"again", "repeat that", "do that again", "one more time", "same again"}
HELP = {"what can i say", "show commands", "help"}
DICTATION_ON = {"start dictation", "dictation mode", "start typing"}
DICTATION_OFF = {"stop dictation", "command mode", "stop typing"}

# Words the engine itself listens for, so the recognizer knows them too.
BUILTIN_PHRASES = WAKE | SLEEP | CANCEL | YES | AGAIN | HELP | DICTATION_ON | DICTATION_OFF | {
    "scratch that", "delete that", "new line", "new paragraph", "times", "twice",
}

FILLER_START = ("please ", "um ", "uh ", "okay ", "ok ", "hey computer ", "computer ")
FILLER_END = (" please", " thanks", " thank you")

MAX_REPEAT = 50
FUZZY_CUTOFF = 0.88

# Spoken punctuation in dictation mode.
DICTATION_WORDS = {
    "comma": ",", "period": ".", "full stop": ".", "question mark": "?",
    "exclamation mark": "!", "exclamation point": "!", "colon": ":",
    "semicolon": ";", "dash": " -", "open quote": ' "', "close quote": '"',
}


@dataclass
class Result:
    heard: str
    handled: bool
    message: str = ""
    command: object = None
    params: dict = field(default_factory=dict)
    times: int = 1


def normalize(text):
    text = text.lower().replace("[unk]", " ").strip()
    text = re.sub(r"[^\w\s'+\-]", " ", text)
    text = " ".join(text.split())
    changed = True
    while changed:
        changed = False
        for f in FILLER_START:
            if text.startswith(f):
                text, changed = text[len(f):], True
        for f in FILLER_END:
            if text.endswith(f):
                text, changed = text[: -len(f)], True
    return normalize_numbers(undo_sounds_like(text))


def split_repeat(text):
    """"nudge right 4 times" -> ("nudge right", 4)."""
    m = re.match(r"^(.*\S)\s+(\d+)\s+times?$", text)
    if m:
        return m.group(1), min(int(m.group(2)), MAX_REPEAT)
    if text.endswith(" twice"):
        return text[: -len(" twice")], 2
    return text, 1


class Engine:
    def __init__(self, platform, packs, feedback=None, start_awake=True, own_names=()):
        """
        platform    from platforms.get_platform()
        packs       from grammar.load_packs()
        feedback    called with a short message after each command (speech, screen)
        own_names   names this app shows up as when it's in front, so commands
                    go to the DAW the user was in, not to our own window
        """
        self.platform = platform
        self.packs = packs
        self.feedback = feedback or (lambda msg: None)
        self.awake = start_awake
        self.dictating = False
        self.pending = None      # (command, params, times) waiting for "yes"
        self.last = None         # (command, params, times) for "again"
        self.own_names = {n.lower() for n in own_names}
        self.target = None       # last app in front that wasn't us
        self._last_typed = ""

    # -- context -------------------------------------------------------

    def _is_own(self, app):
        return app is not None and app.name.lower() in self.own_names

    def note_frontmost(self):
        """Call now and then (the app does, twice a second) to track the user's app."""
        app = self.platform.frontmost()
        if app is not None and not self._is_own(app):
            self.target = app
        return app

    def current_app_name(self):
        app = self.note_frontmost()
        if self._is_own(app) or app is None:
            return self.target.name if self.target else None
        return app.name

    def _bring_target_forward(self):
        """If our own window has focus, hand it back before pressing keys."""
        app = self.platform.frontmost()
        if self._is_own(app) and self.target is not None:
            self.platform.focus(self.target)

    def commands_for(self, app_name):
        """App-specific commands first, so they win over global ones."""
        specific = [c for p in self.packs if not p.is_global and p.applies_to(app_name) for c in p.commands]
        general = [c for p in self.packs if p.is_global for c in p.commands]
        return specific + general

    # -- main entry ----------------------------------------------------

    def handle(self, heard, alternative=None):
        """Act on one utterance.

        heard        the best transcript (from the command-vocabulary recognizer)
        alternative  an open-vocabulary transcript of the same audio, used for
                     dictation and for commands that take free text
        """
        texts = [t for t in (normalize(heard), normalize(alternative or "")) if t]
        raw = heard if normalize(heard) else (alternative or heard)
        if not texts:
            return Result(raw, False)
        text = texts[0]

        if not self.awake:
            if any(t in WAKE for t in texts):
                self.awake = True
                return self._reply(raw, "Listening")
            return Result(raw, False, "asleep")

        if any(t in SLEEP for t in texts):
            self.awake = False
            self.dictating = False
            return self._reply(raw, "Going to sleep")

        if self.dictating:
            # dictation wants the open-vocabulary words, not the command guess
            return self._dictate(alternative or heard, texts)

        if self.pending:
            cmd, params, times = self.pending
            self.pending = None
            if text in YES:
                return self._run(raw, cmd, params, times)
            return self._reply(raw, "Cancelled")

        if text in DICTATION_ON:
            self.dictating = True
            return self._reply(raw, "Dictation on. Say stop dictation to go back to commands.")
        if text in HELP:
            return self._help(raw)
        if text in AGAIN:
            if not self.last:
                return self._reply(raw, "Nothing to repeat yet", handled=False)
            cmd, params, times = self.last
            return self._run(raw, cmd, params, times)
        if text in CANCEL:
            return self._reply(raw, "OK")

        commands = self.commands_for(self.current_app_name())
        found = None
        for t in texts:
            body, times = split_repeat(t)
            found = self._match(body, commands)
            if found:
                raw = t
                break
        if not found:
            body, times = split_repeat(text)
            found = self._fuzzy(body, commands)
        if not found:
            return Result(raw, False, f"Didn't catch a command in \"{text}\"")
        cmd, params = found
        if cmd.repeatable is False:
            times = 1
        if cmd.confirm:
            self.pending = (cmd, params, times)
            return self._reply(raw, f"Say yes to {cmd.help or cmd.phrases[0]}, or cancel")
        return self._run(raw, cmd, params, times)

    # -- helpers -------------------------------------------------------

    def _match(self, text, commands):
        for cmd in commands:
            params = cmd.match(text)
            if params is not None:
                return cmd, params
        return None

    def _fuzzy(self, text, commands):
        """Catch near-misses like "solo the trak" vs "solo the track"."""
        best, best_score = None, FUZZY_CUTOFF
        for cmd in commands:
            if not cmd.fuzzy:
                continue
            for phrase in cmd.literal_phrases:
                score = difflib.SequenceMatcher(None, text, phrase).ratio()
                if score > best_score:
                    best, best_score = cmd, score
        return (best, {}) if best else None

    def _run(self, raw, cmd, params, times):
        action = cmd.action
        if "builtin" in action:
            return self._builtin(raw, action["builtin"])
        self._bring_target_forward()
        app_name = self.target.name if self.target else None
        for i in range(times):
            if i:
                self.platform.wait(0.08)
            run_action(action, params, self.platform, app_name)
        self.last = (cmd, params, times)
        msg = cmd.reply
        for k, v in params.items():
            msg = msg.replace("{" + k + "}", str(v))
        if times > 1 and msg:
            msg += f", {times} times"
        if msg:
            self.feedback(msg)
        return Result(raw, True, msg or cmd.phrases[0], cmd, params, times)

    def _builtin(self, raw, name):
        if name == "dictation":
            self.dictating = True
            return self._reply(raw, "Dictation on")
        if name == "sleep":
            self.awake = False
            return self._reply(raw, "Going to sleep")
        if name == "help":
            return self._help(raw)
        raise ValueError(f"unknown builtin {name!r}")

    def _dictate(self, raw, texts):
        if any(t in DICTATION_OFF for t in texts):
            self.dictating = False
            return self._reply(raw, "Back to commands")
        text = texts[-1]
        self._bring_target_forward()
        if text in ("scratch that", "delete that"):
            for _ in range(len(self._last_typed)):
                self.platform.press("delete")
            self._last_typed = ""
            return Result(raw, True, "Scratched")
        if text in ("new line", "newline"):
            self.platform.press("return")
            return Result(raw, True, "New line")
        if text == "new paragraph":
            self.platform.press("return")
            self.platform.press("return")
            return Result(raw, True, "New paragraph")
        typed = self._format_dictation(raw)
        self.platform.type_text(typed)
        self._last_typed = typed
        return Result(raw, True, f"Typed: {typed.strip()}")

    def _format_dictation(self, raw):
        out = " " + raw.replace("[unk]", "").strip()
        for word, mark in sorted(DICTATION_WORDS.items(), key=lambda kv: -len(kv[0])):
            out = re.sub(rf"\s+{re.escape(word)}\b", mark, out, flags=re.IGNORECASE)
        return out

    def help_lines(self):
        app = self.current_app_name()
        lines = [f"Commands for {app or 'any app'}:"]
        for c in self.commands_for(app):
            lines.append(f"  {c.phrases[0]:<32} {c.pack}")
        return lines

    def _help(self, raw):
        lines = self.help_lines()
        self.feedback(f"{len(lines) - 1} commands available. They're listed on screen.")
        return Result(raw, True, "\n".join(lines))

    def _reply(self, raw, msg, handled=True):
        self.feedback(msg)
        return Result(raw, handled, msg)
