"""Joining the Limitless Sound suite.

With the Limitless Sound hub running:
- Every other app's actions can be spoken: "screen colors on", "one-hand mode on",
  "zoom keys off", "next layer"... Limitless Voice's own commands always win.
- Other apps can use Voice: put it to sleep or wake it, run any spoken command
  ("voice.do"), and press DAW commands (record, undo, save...) for apps that
  can't press keys themselves, like GazeStage.
- Take mode: when any app starts a recording, the hub's take-guard link puts
  Voice in take mode, where only "stop" works. Lyrics can't trigger commands.
- Voice stops listening while the suite's one voice is talking, so it never
  hears another app's announcement.
- The suite's shared text size, high contrast and reduced motion settings
  apply to every Voice window (see look.py), and Voice tells the suite the
  values it's using. So does its language, unless one is chosen in Voice.
- The suite talks in English: the intents and phrases other apps send are
  English, and what Voice reports is too, whatever language it listens in.
Without the hub, none of this does anything.
"""

import re

from . import __version__
from .engine import normalize
from .limitless_link import Link
from .numbers import number_to_words

# Shared DAW intents -> the phrase Limitless Voice runs for it.
INTENT_PHRASES = {
    "daw.playStop": "play stop",
    "daw.play": "play",
    "daw.stop": "stop",
    "daw.record": "record",
    "daw.start": "go to start",
    "daw.undo": "undo",
    "daw.redo": "redo",
    "daw.save": "save",
    "daw.mute": "mute track",
    "daw.solo": "solo track",
    "daw.nextTrack": "next track",
    "daw.prevTrack": "previous track",
    "daw.zoomIn": "zoom in",
    "daw.zoomOut": "zoom out",
    "daw.zoomFit": "zoom to fit",
    "daw.metronome": "metronome",
    "daw.mixer": "mixer",
}

# What was said -> the intent it carried out, so the rest of the suite hears about it.
SPOKEN_INTENTS = {
    "record": "daw.record", "start recording": "daw.record",
    "stop": "daw.stop", "stop playback": "daw.stop", "stop recording": "daw.stop", "stop the take": "daw.stop",
    "play": "daw.play", "start playback": "daw.play", "play stop": "daw.playStop",
    "go to start": "daw.start", "go to beginning": "daw.start", "back to start": "daw.start",
    "undo": "daw.undo", "undo that": "daw.undo", "redo": "daw.redo", "redo that": "daw.redo",
    "save": "daw.save", "save the project": "daw.save", "save project": "daw.save", "save that": "daw.save",
    "mute": "daw.mute", "mute track": "daw.mute", "mute the track": "daw.mute",
    "solo": "daw.solo", "solo track": "daw.solo", "solo the track": "daw.solo",
    "next track": "daw.nextTrack", "track down": "daw.nextTrack",
    "previous track": "daw.prevTrack", "track up": "daw.prevTrack",
    "zoom in": "daw.zoomIn", "zoom out": "daw.zoomOut", "zoom to fit": "daw.zoomFit", "fit": "daw.zoomFit",
    "metronome": "daw.metronome", "click": "daw.metronome",
    "mixer": "daw.mixer", "show the mixer": "daw.mixer", "show mixer": "daw.mixer",
}

OWN_ACTIONS = [
    {"id": "sleep", "label": "Stop listening"},
    {"id": "wake", "label": "Start listening"},
    {"id": "toggle", "label": "Listening on or off"},
    {"id": "takeGuard", "label": "Take mode: only hear stop"},
    {"id": "takeGuardOff", "label": "Take mode off"},
    {"id": "do", "label": "Run a spoken command", "args": {"phrase": "text"}},
] + [{"id": intent.split(".")[1], "label": phrase.capitalize(), "intent": intent}
     for intent, phrase in INTENT_PHRASES.items()]


def spoken_forms(action):
    """Ways to say another app's action: its label (without bracketed notes) and its phrases.
    Plain words, as the recognizer hears them ("one hand mode on")."""
    forms = set()
    for text in [action.get("label", "")] + list(action.get("phrases") or []):
        text = re.sub(r"\(.*?\)", " ", text.lower())
        text = re.sub(r"[^a-z0-9' ]", " ", text.replace("+", " plus "))
        # spell numbers out, so "Layer 2" and "Layer 3" stay different actions
        text = re.sub(r"\d{1,6}", lambda m: f" {number_to_words(int(m.group()))} ", text)
        text = re.sub(r"\d", " ", text)
        text = " ".join(text.split())
        if text and len(text.split()) <= 8:
            forms.add(text)
            if text.endswith(" on or off"):
                forms.add(text[: -len(" on or off")])
    return forms


class Suite:
    def __init__(self, engine, on_change=None, on_phrases=None, on_speaking=None, on_look=None,
                 dispatch=None):
        """
        engine       the voice Engine
        on_change    called after other apps change the listening state, to refresh the window
        on_phrases   called when the suite's vocabulary changes, to update the recognizer
        on_speaking  called with True/False while the suite's one voice talks
        on_look      called when the suite's shared settings change, to restyle every window
        """
        self.engine = engine
        self.on_change = on_change or (lambda: None)
        self.on_phrases = on_phrases or (lambda: None)
        self.on_speaking = on_speaking or (lambda busy: None)
        self.on_look = on_look or (lambda: None)
        self.spoken: dict[str, dict] = {}   # normalized spoken form -> action from another app
        self._words: set[str] = set()       # the same forms as plain words, for the recognizer
        self._listening = None
        self.prefs: dict = {}               # the suite's shared settings; empty until the hub sends them
        self.link = Link("voice", "Limitless Voice", __version__, actions=OWN_ACTIONS,
                         on_invoke=self.invoke, on_event=self.on_event, on_actions=self.on_actions,
                         on_prefs=self.on_prefs, on_connected=self.on_connected, dispatch=dispatch)
        engine.suite = self

    def start(self):
        self.link.start()
        return self

    def stop(self):
        self.link.stop()

    # -- other apps' actions, by voice -------------------------------------

    def on_actions(self, actions):
        spoken, words = {}, set()
        for a in actions:
            if a.get("tool") in ("voice", "daw") or not a.get("live") or a.get("args"):
                continue
            for form in spoken_forms(a):
                words.add(form)
                spoken.setdefault(normalize(form), a)   # matched the way speech is normalized
        changed = words != self._words
        self.spoken, self._words = spoken, words
        if changed:
            self.on_phrases()

    def phrases(self):
        """Extra words for the command recognizer."""
        return set(self._words)

    def match(self, text):
        return self.spoken.get(text)

    def run(self, action):
        self.link.invoke(action["id"])
        return action["label"]

    # -- Voice as a tool for the others ------------------------------------

    def invoke(self, action, args, source):
        e = self.engine
        if action == "sleep":
            e.awake, e.dictating, e.take = False, False, False
        elif action == "wake":
            e.awake = True
        elif action == "toggle":
            e.awake = not e.awake
            e.dictating = e.dictating and e.awake
        elif action == "takeGuard":
            e.take, e.dictating, e.pending = True, False, None
        elif action == "takeGuardOff":
            e.take = False
        elif action == "do":
            phrase = str(args.get("phrase") or "").strip()
            if not phrase:
                return False, e.lang.text('Which command? Send the words to run, like "solo track".')
            return self._run_phrase(phrase)
        elif f"daw.{action}" in INTENT_PHRASES:
            ok, message, asked = self._run_phrase(INTENT_PHRASES[f"daw.{action}"], with_asked=True)
            if not ok and not asked:
                # The DAW commands only exist while Logic Pro or Pro Tools is in front.
                said = e.from_english(INTENT_PHRASES[f"daw.{action}"], everywhere=True)
                message = e.lang.text("{command} works when Logic Pro or Pro Tools is in front.",
                                      command=said[:1].upper() + said[1:])
            return ok, message
        else:
            return False, e.lang.text("Limitless Voice has no action {action}.", action=repr(action))
        self.on_change()
        self.report_state()
        return True, e.lang.text({"sleep": "Asleep", "wake": "Listening", "toggle": "Listening" if e.awake else "Asleep",
                                  "takeGuard": "Take mode: say stop to end the take",
                                  "takeGuardOff": "All commands back on"}[action])

    def _run_phrase(self, phrase, with_asked=False):
        """Run a command for another app, whatever state Voice is in, without changing that state.
        The phrase is English, as the suite talks, or in Voice's own language."""
        e = self.engine
        saved = (e.awake, e.take, e.dictating, e.pending)
        e.awake, e.take, e.dictating, e.pending = True, False, False, None
        try:
            result = e.handle(e.from_english(phrase))
            needs_yes = e.pending is not None
        finally:
            e.awake, e.take, e.dictating, e.pending = saved
        if needs_yes:
            # quit, close and the like need the person's own spoken "yes"
            out = False, e.lang.text("That command needs a spoken yes, so it can't be run from another app.")
        else:
            if result.handled:
                self.report(result)
            out = result.handled, result.message
        return (*out, needs_yes) if with_asked else out

    # -- telling the suite ---------------------------------------------------

    def report(self, result):
        """After a command ran (from speech or another app), tell the suite what it did."""
        if not result.handled or result.command is None:
            return
        # what was said, in English: in another language, the English phrase it stands for
        said = result.heard if result.english is None else result.english
        intent = SPOKEN_INTENTS.get(normalize(said or ""))
        if intent is None:
            intent = next((SPOKEN_INTENTS[p] for p in result.command.english if p in SPOKEN_INTENTS), None)
        if intent:
            self.link.did(intent.split(".")[1], intent)

    def listening(self):
        e = self.engine
        return "asleep" if not e.awake else "take" if e.take else "dictating" if e.dictating else "awake"

    def report_state(self):
        now = self.listening()
        if now != self._listening:
            self._listening = now
            self.link.state("listening", now)

    def on_connected(self, connected):
        if connected:
            self._listening = None
            self.report_state()

    def on_event(self, name, value, source):
        if name == "hub.speaking":
            self.on_speaking(bool(value))

    def on_prefs(self, prefs):
        # from the hub's welcome and every change; kept if the hub closes, so text doesn't shrink
        self.prefs = dict(prefs)
        self.on_look()

    def report_look(self, look):
        """Tell the suite the shared settings Voice honors, with the values it's using now."""
        self.link.state("prefs.applied", dict(look))

    def say(self, text):
        return self.link.say(text)
