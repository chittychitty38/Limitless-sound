import json

import pytest

from uncommando.daws import find_daw, factory_use
from uncommando.engine import KeyEngine
from uncommando.keys import Combo, format_combo, parse_combo, parse_sequence, speak_combo
from uncommando.profiles import Profiles, check_action, describe
from uncommando.runner import Context, Runner


def C(text):
    return parse_combo(text)


# Keys ---------------------------------------------------------------------------

def test_combos_ignore_modifier_order_and_case():
    assert C("alt+cmd+z") == C("CMD+Option+Z") == Combo(frozenset({"alt", "cmd"}), "z")
    assert str(C("cmd+shift+alt+ctrl+z")) == "ctrl+alt+shift+cmd+z"


def test_combo_text_for_people():
    assert format_combo("alt+cmd+z") == "⌥⌘Z"
    assert format_combo("shift+alt+cmd+z") == "⌥⇧⌘Z"
    assert speak_combo("alt+cmd+z") == "Option Command Z"
    assert speak_combo("cmd+]") == "Command Right Bracket"
    assert format_combo("f13") == "F13"


def test_bad_combos_are_refused():
    for bad in ["", "cmd+", "hyper+z", "cmd+alt", "cmd+notakey"]:
        with pytest.raises(ValueError):
            parse_combo(bad)


def test_sequences():
    assert parse_sequence("cmd+a, cmd+c") == [C("cmd+a"), C("cmd+c")]
    assert parse_sequence(["f1", "f2"]) == [C("f1"), C("f2")]
    assert C("cmd++") == C("cmd+=")


# DAWs ---------------------------------------------------------------------------

def test_daws_found_by_bundle_id_and_plugin_host_name():
    assert find_daw("com.apple.logic10") == "logic"
    assert find_daw("Apple Logic") == "logic"
    assert find_daw("com.avid.ProTools") == "protools"
    assert find_daw("Avid Pro Tools") == "protools"
    assert find_daw("com.ableton.live") == "ableton"
    assert find_daw("com.apple.finder") is None
    assert find_daw(None) is None


def test_factory_conflicts():
    assert factory_use("protools", "alt+cmd+z") == {"Restore Last Selection": ["Pro Tools"]}
    assert "Restore Last Selection" in factory_use("daws", "alt+cmd+z")


# Profiles -----------------------------------------------------------------------

def test_default_profile_has_the_split_undo():
    p = Profiles()
    b = p.find("com.apple.logic10", C("alt+cmd+z"))
    assert b.action == {"plugin": "undo"} and b.repeat
    assert p.find("com.avid.ProTools", C("shift+alt+cmd+z")).action == {"plugin": "redo"}
    assert p.find("com.avid.ProTools", C("ctrl+alt+cmd+z")).hold
    # Plain Cmd+Z is left to the DAW: its own undo, which can leave plugins out.
    assert p.find("com.apple.logic10", C("cmd+z")) is None
    # Outside DAWs nothing changes.
    assert p.find("com.apple.finder", C("alt+cmd+z")) is None


def test_most_specific_profile_wins_and_pass_lets_the_app_have_it():
    p = Profiles()
    p.set_binding("logic", {"keys": "alt+cmd+z", "do": {"plugin": "undoFront"}})
    p.set_binding("protools", {"keys": "alt+cmd+z", "do": {"pass": True}})
    p.set_binding("*", {"keys": "f13", "do": {"say": "hello"}})
    assert p.find("com.apple.logic10", C("alt+cmd+z")).action == {"plugin": "undoFront"}
    assert p.find("com.avid.ProTools", C("alt+cmd+z")).passes
    assert p.find("com.ableton.live", C("alt+cmd+z")).action == {"plugin": "undo"}
    assert p.find("com.apple.finder", C("f13")).action == {"say": "hello"}
    # A profile for any app, by its bundle id.
    p.set_binding("com.example.synth", {"keys": "f13", "do": {"keys": "cmd+s"}})
    assert p.find("com.example.synth", C("f13")).action == {"keys": "cmd+s"}


def test_setting_a_binding_replaces_the_same_keys_and_can_move_keys():
    p = Profiles()
    p.set_binding("logic", {"keys": "f1", "do": {"keys": "cmd+s"}})
    p.set_binding("logic", {"keys": "F1", "do": {"keys": "cmd+b"}})
    assert len(p.bindings("logic")) == 1
    p.set_binding("logic", {"keys": "f2", "do": {"keys": "cmd+b"}}, replacing="f1")
    assert [b["keys"] for b in p.bindings("logic")] == ["f2"]
    p.remove_binding("logic", "f2")
    assert p.bindings("logic") == []


def test_actions_are_checked():
    assert check_action({"keys": "cmd+z"}) is None
    assert check_action({"menu": "Edit > Undo History…"}) is None
    assert check_action({"steps": [{"keys": "cmd+a"}, {"wait": 0.1}, {"menu": ["Edit", "Copy"]}]}) is None
    assert check_action({"plugin": "undo"}) is None
    assert check_action({"menu": "Edit"})
    assert check_action({"plugin": "explode"})
    assert check_action({"keys": "cmd+z", "say": "x"})
    assert check_action({"steps": [{"steps": [{"keys": "a"}]}]})
    assert check_action({"wait": 60})
    with pytest.raises(ValueError):
        Profiles().set_binding("logic", {"keys": "f1", "do": {"plugin": "explode"}})


def test_descriptions_are_plain_words():
    assert describe({"keys": "cmd+a, cmd+c"}) == "Press ⌘A, then ⌘C"
    assert describe({"menu": "Edit > Undo History…"}) == "Choose Edit › Undo History…"
    assert describe({"plugin": "undo"}) == "Undo the last plugin change"


def test_bad_bindings_in_a_file_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(json.dumps({"version": 1, "apps": {"logic": {"bindings": [
        {"keys": "f1", "do": {"keys": "cmd+s"}},
        {"keys": "cmd+nope", "do": {"keys": "cmd+s"}},
        {"keys": "f2", "do": {"plugin": "explode"}},
        {"keys": "f3", "do": {"keys": "cmd+s"}, "on": False}]}}}))
    p = Profiles.load(path)
    assert p.find("com.apple.logic10", C("f1"))
    assert p.find("com.apple.logic10", C("f3")) is None
    assert len(p.problems) == 2


def test_broken_file_is_kept_aside(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text("{not json")
    p = Profiles.load(path)
    assert p.find("com.apple.logic10", C("alt+cmd+z"))
    assert (tmp_path / "shortcuts.broken.json").exists()


def test_save_import_export(tmp_path):
    p = Profiles(path=tmp_path / "a.json")
    p.set_binding("logic", {"keys": "f1", "do": {"keys": "cmd+s"}})
    p.save()
    assert Profiles.load(tmp_path / "a.json").find("com.apple.logic10", C("f1"))
    p.export_to(tmp_path / "share.json")
    q = Profiles()
    q.set_binding("logic", {"keys": "f2", "do": {"keys": "cmd+b"}})
    q.import_from(tmp_path / "share.json")
    assert q.find("com.apple.logic10", C("f1")) and q.find("com.apple.logic10", C("f2"))
    (tmp_path / "junk.json").write_text("[]")
    with pytest.raises(ValueError):
        q.import_from(tmp_path / "junk.json")


def test_notes_warn_about_what_a_shortcut_replaces():
    p = Profiles()
    assert any("Restore Last Selection" in n for n in p.notes_for("protools", "alt+cmd+z"))
    assert any("typing" in n for n in p.notes_for("logic", "z"))
    assert p.notes_for("logic", "f13") == []


def test_active_lists_what_works_in_an_app():
    p = Profiles()
    p.set_binding("logic", {"keys": "alt+cmd+z", "do": {"plugin": "undoFront"}})
    active = {str(b.combo): b.action for b in p.active("com.apple.logic10")}
    assert active[str(C("alt+cmd+z"))] == {"plugin": "undoFront"}
    assert active[str(C("shift+alt+cmd+z"))] == {"plugin": "redo"}


# Engine ----------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_engine():
    calls = []
    clock = Clock()
    engine = KeyEngine(Profiles(), lambda b, phase, app, pid: calls.append((str(b.combo), phase)), clock)
    return engine, calls, clock


LOGIC = "com.apple.logic10"
ALT_CMD = frozenset({"alt", "cmd"})


def test_engine_keeps_shortcut_from_the_daw_and_runs_it():
    e, calls, _ = make_engine()
    assert e.handle(ALT_CMD, "z", True, False, LOGIC) is True
    assert e.handle(ALT_CMD, "z", False, False, LOGIC) is True   # its key-up too
    assert calls == [("alt+cmd+z", "down")]


def test_engine_lets_everything_else_through():
    e, calls, _ = make_engine()
    assert e.handle(frozenset({"cmd"}), "z", True, False, LOGIC) is False
    assert e.handle(frozenset({"cmd"}), "z", False, False, LOGIC) is False
    assert e.handle(ALT_CMD, "z", True, False, "com.apple.finder") is False
    assert e.handle(frozenset(), None, True, False, LOGIC) is False
    assert calls == []


def test_held_shortcut_repeats_at_a_safe_rate():
    e, calls, clock = make_engine()
    e.handle(ALT_CMD, "z", True, False, LOGIC)
    for i in range(10):
        clock.t += 0.03
        assert e.handle(ALT_CMD, "z", True, True, LOGIC) is True
    phases = [p for _, p in calls]
    assert phases[0] == "down" and 2 <= phases.count("repeat") <= 4


def test_hold_shortcut_gets_its_key_up():
    e, calls, _ = make_engine()
    mods = frozenset({"ctrl", "alt", "cmd"})
    e.handle(mods, "z", True, False, LOGIC)
    e.handle(mods, "z", True, True, LOGIC)       # compare doesn't repeat
    e.handle(frozenset(), "z", False, False, LOGIC)   # modifiers let go first
    assert calls == [("ctrl+alt+cmd+z", "down"), ("ctrl+alt+cmd+z", "up")]


def test_paused_engine_only_answers_its_pause_key():
    e, calls, _ = make_engine()
    e.profiles.set_binding("*", {"keys": "f15", "do": {"app": "pause"}})
    e.enabled = False
    assert e.handle(ALT_CMD, "z", True, False, LOGIC) is False
    assert e.handle(frozenset(), "f15", True, False, LOGIC) is True
    assert calls == [("f15", "down")]


def test_capture_takes_the_next_shortcut():
    e, calls, _ = make_engine()
    got = []
    e.capture_next(got.append)
    assert e.handle(frozenset({"cmd", "shift"}), "k", True, False, LOGIC) is True
    assert e.handle(frozenset({"cmd", "shift"}), "k", False, False, LOGIC) is True
    assert got == [C("shift+cmd+k")] and calls == []


# Runner -----------------------------------------------------------------------------

class FakeBackend:
    def __init__(self):
        self.did = []

    def send(self, combo, pid=None):
        self.did.append(("key", str(combo), pid))

    def press_menu(self, pid, path):
        self.did.append(("menu", path))
        return True, ""

    def press_button(self, pid, name):
        self.did.append(("button", name))
        return False, f"Couldn't find a {name} button"

    def type_text(self, text):
        self.did.append(("type", text))


class FakePlugins:
    def __init__(self):
        self.did = []

    def undo(self, ctx):
        self.did.append("undo")
        return True, "Plugin undo"

    def redo(self, ctx):
        self.did.append("redo")
        return False, "No plugin changes to redo."

    def compare(self, down, ctx):
        self.did.append("before" if down else "after")
        return True, "x"


def make_runner():
    backend, plugins, said, app = FakeBackend(), FakePlugins(), [], []
    r = Runner(backend, plugins, lambda fn: fn(), lambda text, ok, speak: said.append((text, ok, speak)),
               lambda name, ctx: app.append(name), lambda action, args: action == "zoom.in")
    return r, backend, plugins, said, app


def test_runner_does_each_kind_of_action():
    r, backend, plugins, said, app = make_runner()
    ctx = Context(LOGIC, 42)
    r.run_now({"steps": [{"keys": "cmd+a, cmd+c"}, {"wait": 0}, {"menu": "Edit > Paste"},
                         {"type": "hi"}, {"say": "done"}, {"app": "cheatSheet"}, {"suite": "zoom.in"}]},
              ctx=ctx)
    assert backend.did == [("key", "cmd+a", 42), ("key", "cmd+c", 42), ("menu", ["Edit", "Paste"]),
                           ("type", "hi")]
    assert said == [("done", True, True)] and app == ["cheatSheet"]


def test_runner_reports_what_went_wrong():
    r, backend, plugins, said, app = make_runner()
    r.run_now({"button": "Bounce"})
    r.run_now({"suite": "color.on"})
    assert said[0] == ("Couldn't find a Bounce button", False, True)
    assert "hub" in said[1][0]


def test_runner_plugin_actions_and_quiet_repeats():
    r, backend, plugins, said, app = make_runner()
    r.run_now({"plugin": "undo"}, "down")
    r.run_now({"plugin": "undo"}, "repeat")
    r.run_now({"plugin": "redo"}, "repeat")
    r.run_now({"plugin": "compare"}, "down")
    r.run_now({"plugin": "compare"}, "up")
    r.run_now({"plugin": "undo"}, "up")             # key-up of a non-hold shortcut does nothing
    assert plugins.did == ["undo", "undo", "redo", "before", "after"]
    assert said[0] == ("Plugin undo", True, True)
    assert said[1] == ("Plugin undo", True, False)   # held down: shown, not said again
    assert said[2] == ("No plugin changes to redo.", False, True)
