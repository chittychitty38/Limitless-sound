import pytest

from limitless_control import keys, profiles
from limitless_control.app import validate
from limitless_control.engine import Engine, find_profile


class Recorder:
    def __init__(self):
        self.sent, self.spoken, self.logs = [], [], []

    def send(self, k):
        self.sent.append(k)

    def speak(self, text):
        self.spoken.append(text)

    def log(self, text):
        self.logs.append(text)


@pytest.fixture
def out():
    return Recorder()


def make_engine(out, layer_mode="oneShot"):
    config = {
        "timing": {"minPressSeconds": 0.05, "cooldownSeconds": 0.1, "longPressSeconds": 0.8,
                   "repeatDelaySeconds": 0.5, "repeatIntervalSeconds": 0.1},
        "speak": True,
        "layerMode": layer_mode,
        "global": {
            "view": {"tap": {"command": "layer"}},
            "menu": {"tap": {"command": "announce"}, "hold": {"command": "toggleEnabled"}},
        },
        "profiles": [
            {"name": "Logic Pro", "apps": ["com.apple.logic10"], "layers": [
                {
                    "a": {"tap": {"keys": "space", "say": "Play stop"}},
                    "b": {"tap": {"keys": "return"}, "hold": {"keys": "r", "say": "Record"}},
                    "lt": {"tap": {"keys": "mod+left"}, "repeats": True},
                },
                {"a": {"tap": {"keys": "mod+s", "say": "Saved"}}},
            ]},
            {"name": "Pro Tools", "apps": ["com.avid.protools", "protools.exe"], "layers": [
                {"a": {"tap": {"keys": "space"}}},
            ]},
            {"name": "Everyday", "apps": ["*"], "layers": [{"a": {"tap": {"keys": "return"}}}]},
        ],
    }
    e = Engine(config, out)
    e.app_changed("com.apple.logic10")
    out.spoken.clear()
    return e


def tap(e, name, at, length=0.1):
    e.press(name, at)
    e.tick(at + length)
    e.release(name, at + length)


def test_tap_fires_once_after_min_press(out):
    e = make_engine(out)
    e.press("a", 0)
    assert out.sent == []
    e.tick(0.06)
    e.tick(2.0)
    e.release("a", 2.0)
    assert out.sent == ["space"]
    assert out.spoken == ["Play stop"]


def test_busy_only_while_a_switch_is_held(out):
    """The main loop slows down when nothing is held, so it must know when something is."""
    e = make_engine(out)
    assert not e.busy
    e.press("b", 0)
    assert e.busy
    e.tick(1.0)              # the long press fires...
    assert e.busy            # ...and the switch is still down
    e.release("b", 1.2)
    assert not e.busy


def test_tremor_bump_ignored(out):
    e = make_engine(out)
    e.press("a", 0)
    e.tick(0.02)
    e.release("a", 0.03)
    assert out.sent == []


def test_cooldown_blocks_double_hit(out):
    e = make_engine(out)
    tap(e, "a", 0)
    tap(e, "a", 0.15)
    tap(e, "a", 0.5)
    assert len(out.sent) == 2


def test_tap_versus_hold(out):
    e = make_engine(out)
    tap(e, "b", 0, length=0.3)
    assert out.sent == ["return"]
    e.press("b", 1)
    e.tick(1.9)
    e.release("b", 2.5)
    assert out.sent == ["return", "r"]
    assert out.spoken == ["Record"]


def test_repeat_while_held(out):
    e = make_engine(out)
    e.press("lt", 0)
    t = 0.0
    while t < 1.0:
        t += 0.015
        e.tick(t)
    e.release("lt", t)
    assert 5 <= len(out.sent) <= 7
    assert set(out.sent) == {"mod+left"}


def test_one_shot_layer(out):
    e = make_engine(out)
    tap(e, "view", 0)
    assert e.layer == 1
    tap(e, "a", 1)
    assert out.sent == ["mod+s"]
    assert e.layer == 0
    tap(e, "a", 2)
    assert out.sent[-1] == "space"


def test_toggle_layer_stays(out):
    e = make_engine(out, "toggle")
    tap(e, "view", 0)
    tap(e, "a", 1)
    tap(e, "a", 2)
    assert out.sent == ["mod+s", "mod+s"]
    tap(e, "view", 3)
    assert e.layer == 0


def test_on_off_switch(out):
    e = make_engine(out)
    e.press("menu", 0)
    e.tick(0.9)
    e.release("menu", 1.0)
    assert not e.enabled
    assert out.spoken[-1] == "Controller off"
    tap(e, "a", 2)
    assert out.sent == []
    e.press("menu", 3)
    e.tick(3.9)
    e.release("menu", 4)
    assert e.enabled
    tap(e, "a", 5)
    assert out.sent == ["space"]


def test_switching_off_drops_held_switches(out):
    e = make_engine(out)
    e.press("lt", 0)
    e.tick(0.1)
    e.set_enabled(False)
    e.tick(1.0)
    assert out.sent == ["mod+left"]


def test_menu_tap_announces(out):
    e = make_engine(out)
    tap(e, "menu", 0, length=0.2)
    assert out.spoken == ["Logic Pro, layer 1"]


def test_profile_follows_app(out):
    e = make_engine(out)
    e.app_changed("ProTools.exe")
    assert e.profile["name"] == "Pro Tools"
    e.app_changed("com.apple.Safari")
    assert e.profile["name"] == "Everyday"
    assert out.spoken == ["Pro Tools", "Everyday"]
    tap(e, "a", 0)
    assert out.sent == ["return"]


def test_wildcard_app_patterns():
    config = profiles.default_config()
    assert find_profile(config, "ableton live 12 suite.exe")["name"] == "Ableton Live"
    assert find_profile(config, "com.ableton.live")["name"] == "Ableton Live"
    assert find_profile(config, "notepad.exe")["name"] == "Everyday"
    assert find_profile(config, None)["name"] == "Everyday"


def test_garageband_reaper_and_fl_studio_are_found():
    config = profiles.default_config()
    for app_id, name in [("com.apple.garageband10", "GarageBand"), ("com.cockos.reaper", "REAPER"),
                         ("com.cockos.reaper64", "REAPER"), ("reaper.exe", "REAPER"),
                         ("com.image-line.flstudio", "FL Studio"), ("fl64.exe", "FL Studio"),
                         ("fl64 (scaled).exe", "FL Studio"), ("com.apple.garageband", "Everyday")]:
        assert find_profile(config, app_id)["name"] == name, app_id


def test_settings_from_before_get_the_new_daws(tmp_path):
    # Saved by an older version: Logic, Pro Tools, Ableton and Everyday, one of them changed.
    old = profiles.default_config()
    old["profiles"] = [p for p in old["profiles"] if p["name"] not in ("GarageBand", "REAPER", "FL Studio")]
    old["profiles"][0]["layers"][0]["a"] = {"tap": {"keys": "k"}}
    path = tmp_path / "settings.json"
    profiles.save(old, path)
    config = profiles.load(path)
    assert [p["name"] for p in config["profiles"]] == ["Logic Pro", "Pro Tools", "Ableton Live", "GarageBand",
                                                      "REAPER", "FL Studio", "Everyday"]
    assert config["profiles"][0]["layers"][0]["a"] == {"tap": {"keys": "k"}}   # theirs, kept
    assert validate(config) == []
    assert find_profile(config, "reaper.exe")["name"] == "REAPER"


def test_fl_studio_has_no_record_or_redo():
    # R only switches record mode (play then records), and Ctrl/Cmd+Z undoes and redoes in turn:
    # neither may answer the suite's "record" or "redo", and undo steps back through the history.
    fl = profiles.CATALOG["FL Studio"]
    assert "record" not in fl and "redo" not in fl
    assert fl["record_mode"]["keys"] == "r" and fl["undo"]["keys"] == "mod+alt+z"
    # REAPER's redo is Ctrl+Shift+Z on Windows too, not Ctrl+Y.
    assert profiles.CATALOG["REAPER"]["redo"]["keys"] == "mod+shift+z"


def test_speech_off(out):
    e = make_engine(out)
    e.config["speak"] = False
    tap(e, "a", 0)
    assert out.spoken == []


@pytest.mark.parametrize("text,expected", [
    ("mod+shift+z", ({"mod", "shift"}, "z")),
    ("cmd+left", ({"mod"}, "left")),
    ("opt+return", ({"alt"}, "return")),
    ("ctrl+;", ({"ctrl"}, ";")),
    ("keypad7", (set(), "keypad7")),
])
def test_parse(text, expected):
    mods, key = keys.parse(text)
    assert (set(mods), key) == expected


@pytest.mark.parametrize("bad", ["", "mod+", "a+b", "mod+nope", "shift"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        keys.parse(bad)


def test_resolve_per_platform():
    k = {"mac": "ctrl+p", "windows": "win+p"}
    assert keys.resolve(k, "mac") == "ctrl+p"
    assert keys.resolve(k, "windows") == "win+p"
    assert keys.resolve(k, "linux") == "win+p"
    assert keys.resolve("space", "mac") == "space"


def test_describe():
    assert keys.describe("mod+shift+z", "mac") == "Shift ⌘ Z"
    assert keys.describe("mod+shift+z", "windows") == "Ctrl+Shift+Z"


def test_default_config_is_valid():
    config = profiles.default_config()
    assert validate(config) == []
    assert [p["name"] for p in config["profiles"]] == ["Logic Pro", "Pro Tools", "Ableton Live", "GarageBand",
                                                      "REAPER", "FL Studio", "Everyday"]
    # Record never sits on a tap of a big button.
    for p in config["profiles"]:
        for inp in ("a", "b"):
            tap_action = p["layers"][0].get(inp, {}).get("tap") or {}
            assert tap_action.get("id") != "record", p["name"]


def test_validate_reports_bad_keys():
    config = profiles.default_config()
    config["profiles"][0]["layers"][0]["a"]["tap"] = {"keys": "mod+banana"}
    problems = validate(config)
    assert len(problems) == 1 and "banana" in problems[0]


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    config = profiles.default_config()
    config["speak"] = False
    profiles.save(config, path)
    assert profiles.load(path)["speak"] is False


def test_broken_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert profiles.load(path)["profiles"]
    assert (tmp_path / "settings.broken.json").exists()
