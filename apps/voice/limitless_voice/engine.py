"""The voice command engine: takes recognized text, decides what to do.

It knows four states:
  asleep     ignores everything except a wake phrase, so talking to a
             bandmate or singing a take never triggers anything
  take       during a recording: only "stop" (and the sleep and wake words)
             do anything, so lyrics can't trigger commands mid-take
  command    matches phrases against the packs for the app in front
  dictation  types what you say into the focused field
"""

import difflib
import re
from dataclasses import dataclass, field

from .actions import _fill, run_action
from .grammar import undo_sounds_like
from .numbers import normalize_numbers

WAKE = {"wake up", "start listening", "computer wake up"}
SLEEP = {"go to sleep", "stop listening"}
CANCEL = {"cancel", "never mind", "nevermind", "no"}
YES = {"yes", "confirm", "do it", "yes please"}
AGAIN = {"again", "repeat that", "do that again", "one more time", "same again"}
HELP = {"what can i say", "show commands", "help"}
DICTATION_ON = {"start dictation", "dictation mode", "start typing", "begin dictation", "dictation on", "take dictation"}
DICTATION_OFF = {"stop dictation", "command mode", "stop typing", "end dictation", "dictation off"}
# While a take is recording, only these do anything.
TAKE_STOP = {"stop", "stop recording", "stop playback", "stop the take"}
TAKE_OFF = {"end take mode", "take mode off", "all commands"}

# Words the engine itself listens for, so the recognizer knows them too.
BUILTIN_PHRASES = WAKE | SLEEP | CANCEL | YES | AGAIN | HELP | DICTATION_ON | DICTATION_OFF | TAKE_STOP | TAKE_OFF | {
    "scratch that", "delete that", "new line", "new paragraph", "times", "twice",
}

FILLER_START = ("please ", "um ", "uh ", "okay ", "ok ", "hey computer ", "computer ")
FILLER_END = (" please", " thanks", " thank you")

MAX_REPEAT = 50
# Keys that throw work away. However they're reached ("delete fifty times",
# "press backspace twenty times"), one utterance presses them at most this often.
DESTRUCTIVE_KEYS = {"delete", "backspace", "forwarddelete", "cmd+x", "cmd+v", "cmd+d", "cmd+delete",
                    "cmd+backspace", "ctrl+x", "ctrl+v", "ctrl+d"}
MAX_DESTRUCTIVE = 3
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
        self.take = False        # a take is recording: only stop words count
        self.suite = None        # the Limitless Sound link: other apps' actions by voice
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
        # The command recognizer's guess at a sentence it mostly couldn't place ("[unk] enter [unk]
        # [unk]") isn't a command on its own: in an hour of people reading aloud, nearly every
        # command that fired came from one (stress/test_voice_real_speech.py). Then only the open
        # transcript counts.
        if alternative is not None and heard.lower().split().count("[unk]") > len(normalize(heard).split()):
            texts = [t for t in (normalize(alternative),) if t]
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

        if self.take:
            if any(t in TAKE_OFF for t in texts):
                self.take = False
                return self._reply(raw, "All commands back on")
            if not any(t in TAKE_STOP for t in texts):
                return Result(raw, False, "take")
            self.take = False
            found = self._match("stop", self.commands_for(self.current_app_name()))
            if found:
                return self._run(raw, found[0], found[1], 1)
            return self._reply(raw, "All commands back on")

        if self.dictating:
            # dictation wants the open-vocabulary words, not the command guess
            return self._dictate(alternative or heard, texts)

        if self.pending:
            cmd, params, times = self.pending
            self.pending = None
            if text in YES:
                return self._run(raw, cmd, params, times)
            if text in CANCEL:
                return self._reply(raw, "Cancelled")
            # Anything else is the next command: a question asked by mistake mustn't eat it.

        if text in DICTATION_ON:
            self.dictating = True
            return self._reply(raw, "Dictation on. Say stop dictation to go back to commands.")
        if text in DICTATION_OFF:
            # "start" and "stop" sound alike to the recognizer; dictation is already off,
            # so a "stop" here was most likely a "start" misheard
            return self._reply(raw, "Dictation is off. To start it, say begin dictation.", handled=False)
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
        found, said = None, text
        for t in texts:
            body, times = split_repeat(t)
            found = self._match(body, commands)
            if found:
                raw = said = t
                break
        if not found and self.suite is not None:
            for t in texts:
                hit = self.suite.match(t)
                if hit:
                    return self._reply(raw, self.suite.run(hit))
        if not found:
            body, times = split_repeat(text)
            found = self._fuzzy(body, commands)
        if not found:
            elsewhere = self._works_in(texts)
            if elsewhere:
                # Heard right, but it's a DAW command and that DAW isn't in front.
                return Result(raw, False, f"\"{text}\" works in {elsewhere}. "
                              f"Bring {'it' if ' and ' not in elsewhere else 'one of them'} to the front, "
                              "then say it again.")
            return Result(raw, False, f"Didn't catch a command in \"{text}\"")
        cmd, params = found
        # Free text from the command recognizer is only the command words it could place: "open the
        # [unk] [unk] that" tried to open an app called "the that". When it missed words, the
        # words come from the open recognizer, or the command doesn't run.
        if (cmd.free_text and alternative is not None and "[unk]" in heard.lower()
                and said == normalize(heard) != normalize(alternative)):
            heard_open = normalize(alternative)
            again = self._match(split_repeat(heard_open)[0], [cmd])
            if not again:
                return Result(raw, False, f"Didn't catch a command in \"{heard_open}\"" if heard_open
                              else "Didn't catch that")
            params, raw = again[1], heard_open
        if cmd.repeatable is False:
            times = 1
        elif not isinstance(cmd.repeatable, bool) and isinstance(cmd.repeatable, int):
            times = min(times, max(1, cmd.repeatable))
        if any(str(v).lower() in DESTRUCTIVE_KEYS for v in params.values()):
            times = min(times, MAX_DESTRUCTIVE)
        # A stray word must never throw work away. The command recognizer can only answer with
        # command words, so real people's "cat" came back as "cut" 64 times in 100, and once as
        # "cut that" (stress/test_voice_real_speech.py). A command that would press Cut, Paste or
        # Delete runs at once only if the open recognizer heard its first word too; otherwise Voice
        # asks. Refusing instead missed most of real people's "cut", "paste" and "delete" (40 to 46%
        # right, against 78 to 92% without the check: stress/test_command_words.py), since the open
        # recognizer hears "cut" as "god" and "delete" as "the lead".
        unsure = (alternative is not None and self._destroys(cmd, params)
                  and said.split()[0] not in normalize(alternative).split())
        if cmd.confirm or unsure:
            self.pending = (cmd, params, times)
            return self._reply(raw, f"Say yes to {cmd.help or cmd.phrases[0]}, or cancel")
        return self._run(raw, cmd, params, times)

    def instant(self, heard):
        """Whether the command recognizer's words so far are, exactly, a command to run the moment
        it's said (play, stop, record; stop in take mode), so the listener needn't wait for the
        end of the utterance. Called from the listener's thread, so it only reads, and doesn't
        ask which app is in front: handle() decides that on the main thread as usual."""
        if not self.awake or self.dictating or self.pending or "[unk]" in heard:
            return False
        text = normalize(heard)
        if self.take:
            return text in TAKE_STOP
        return any(cmd.instant and cmd.match(text) is not None for pack in self.packs for cmd in pack.commands)

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _destroys(cmd, params):
        """Whether running the command presses a key that throws work away (Delete, Cut, Paste)."""
        def chords(spec):
            if isinstance(spec, dict):
                if "steps" in spec:
                    for step in spec["steps"]:
                        yield from chords(step)
                elif "keys" in spec:
                    yield from spec["keys"] if isinstance(spec["keys"], list) else [spec["keys"]]
        return any(str(c).replace(" ", "").lower() in DESTRUCTIVE_KEYS for c in chords(_fill(cmd.action, params)))

    def _match(self, text, commands):
        for cmd in commands:
            params = cmd.match(text)
            if params is not None:
                return cmd, params
        return None

    def _works_in(self, texts):
        """The apps where this phrase is a command, when the app in front has none: "Logic Pro and
        Pro Tools". Exact matches only, so a near-miss is never sent off to another app."""
        names = []
        for pack in self.packs:
            if pack.is_global or pack.name in names:
                continue
            if any(self._match(split_repeat(t)[0], pack.commands) for t in texts):
                names.append(pack.name)
        if len(names) > 1:
            return ", ".join(names[:-1]) + " and " + names[-1]
        return names[0] if names else ""

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
