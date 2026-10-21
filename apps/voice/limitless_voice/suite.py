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
Without the hub, none of this does anything.
"""

import re

from . import __version__
from .engine import normalize
from .limitless_link import Link

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
        text = re.sub(r"[^a-z' ]", " ", text.replace("+", " plus "))
        text = " ".join(text.split())
        if text and len(text.split()) <= 8:
            forms.add(text)
            if text.endswith(" on or off"):
                forms.add(text[: -len(" on or off")])
    return forms


class Suite:
    def __init__(self, engine, on_change=None, on_phrases=None, on_speaking=None, dispatch=None):
        """
        engine       the voice Engine
        on_change    called after other apps change the listening state, to refresh the window
        on_phrases   called when the suite's vocabulary changes, to update the recognizer
        on_speaking  called with True/False while the suite's one voice talks
        """
        self.engine = engine
        self.on_change = on_change or (lambda: None)
        self.on_phrases = on_phrases or (lambda: None)
        self.on_speaking = on_speaking or (lambda busy: None)
        self.spoken: dict[str, dict] = {}   # normalized spoken form -> action from another app
        self._words: set[str] = set()       # the same forms as plain words, for the recognizer
        self._listening = None
        self.link = Link("voice", "Limitless Voice", __version__, actions=OWN_ACTIONS,
                         on_invoke=self.invoke, on_event=self.on_event, on_actions=self.on_actions,
                         on_connected=self.on_connected, dispatch=dispatch)
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
        elif action == "do" or f"daw.{action}" in INTENT_PHRASES:
            phrase = args.get("phrase", "") if action == "do" else INTENT_PHRASES[f"daw.{action}"]
            return self._run_phrase(str(phrase))
        else:
            return False, f"Limitless Voice has no action {action!r}."
        self.on_change()
        self.report_state()
        return True, {"sleep": "Asleep", "wake": "Listening", "toggle": "Listening" if e.awake else "Asleep",
                      "takeGuard": "Take mode: say stop to end the take", "takeGuardOff": "All commands back on"}[action]

    def _run_phrase(self, phrase):
        """Run a command for another app, whatever state Voice is in, without changing that state."""
        e = self.engine
        saved = (e.awake, e.take, e.dictating, e.pending)
        e.awake, e.take, e.dictating, e.pending = True, False, False, None
        try:
            result = e.handle(phrase)
        finally:
            e.awake, e.take, e.dictating, _ = saved
        if result.handled:
            self.report(result)
        return result.handled, result.message

    # -- telling the suite ---------------------------------------------------

    def report(self, result):
        """After a command ran (from speech or another app), tell the suite what it did."""
        if not result.handled or result.command is None:
            return
        intent = SPOKEN_INTENTS.get(normalize(result.heard or ""))
        if intent is None:
            intent = next((SPOKEN_INTENTS[p] for p in result.command.phrases if p in SPOKEN_INTENTS), None)
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

    def say(self, text):
        return self.link.say(text)
