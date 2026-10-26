import json
import socket
import threading
import time

from limitless_keys.logic_windows import LogicWindows
from limitless_keys.plugin_undo import PluginUndo
from limitless_keys.runner import Context
from limitless_keys.timeline import Timeline
from limitless_keys.undo_link import LinkServer


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeLink:
    def __init__(self):
        self.sent = []
        self.down = set()

    def send(self, key, msg):
        if key in self.down:
            return False
        self.sent.append((key, msg["op"], msg["id"]))
        return True


class FakeWindows:
    def __init__(self):
        self.pressed = []
        self.closed = set()
        self.front_key = (None, None)

    def press(self, key, which):
        if key in self.closed:
            return False
        self.pressed.append((key, which))
        return True

    def front(self, pid):
        return self.front_key


LOGIC = Context("com.apple.logic10", 100)
PT = Context("com.avid.ProTools", 200)


def setup():
    clock = Clock()
    pu = PluginUndo(clock=clock)
    pu.link, pu.windows = FakeLink(), FakeWindows()
    return pu, clock


def hello(pu, key, pid, host, plugin, track=""):
    pu.link_message(key, {"op": "hello", "pid": pid, "host": host, "plugin": plugin, "track": track})


def step(pu, clock, key, sid, label="Gain", before="0 dB", after="3 dB"):
    clock.t += 1
    pu.link_message(key, {"op": "step", "id": sid, "label": label, "before": before, "after": after})


def test_undo_goes_newest_first_across_plugins():
    pu, clock = setup()
    hello(pu, "eq", 200, "Avid Pro Tools", "Pro-Q 3", "Bass")
    hello(pu, "comp", 200, "Avid Pro Tools", "1176", "Vocal")
    step(pu, clock, "eq", 1, "Band 2 Gain", "-3.1 dB", "+2.4 dB")
    step(pu, clock, "comp", 1, "Attack")
    step(pu, clock, "eq", 2, "Band 2 Freq")
    assert pu.undo(PT) == (True, "Plugin undo: Band 2 Freq back to 0 dB · Pro-Q 3 on Bass")
    assert pu.undo(PT)[1].startswith("Plugin undo: Attack")
    ok, said = pu.undo(PT)
    assert said == "Plugin undo: Band 2 Gain back to -3.1 dB · Pro-Q 3 on Bass"
    assert pu.undo(PT) == (False, "No plugin changes to undo.")
    assert pu.link.sent == [("eq", "undo", 2), ("comp", "undo", 1), ("eq", "undo", 1)]
    # Redo comes back in the reverse order of the undos.
    assert pu.redo(PT)[1].startswith("Plugin redo: Band 2 Gain to +2.4 dB")
    assert pu.redo(PT)[1].startswith("Plugin redo: Attack")
    assert pu.redo(PT)[1].startswith("Plugin redo: Band 2 Freq")
    assert pu.redo(PT)[0] is False


def test_a_new_change_ends_that_plugins_redo_only():
    pu, clock = setup()
    hello(pu, "a", 200, "Avid Pro Tools", "A")
    hello(pu, "b", 200, "Avid Pro Tools", "B")
    step(pu, clock, "a", 1)
    step(pu, clock, "b", 1)
    pu.undo(PT)
    pu.undo(PT)
    step(pu, clock, "b", 2)     # a new change in B: B's undone step can't come back
    src, s = pu.timeline.next_redo(200, "protools")
    assert (src.key, s.id) == ("a", 1)
    pu.redo(PT)
    assert pu.redo(PT)[0] is False


def test_only_the_daw_in_front_is_touched():
    pu, clock = setup()
    hello(pu, "pt", 200, "Avid Pro Tools", "PT plugin")
    hello(pu, "lg", 100, "Apple Logic", "Logic plugin")
    step(pu, clock, "pt", 1)
    step(pu, clock, "lg", 1)
    ok, said = pu.undo(PT)
    assert "PT plugin" in said
    # A voice command while our own window is in front goes to the last DAW used.
    pu.last_daw = ("com.apple.logic10", 100)
    ok, said = pu.undo(Context("org.limitlesssound.keys", 5))
    assert "Logic plugin" in said


def test_plugin_in_a_helper_process_still_counts():
    pu, clock = setup()
    hello(pu, "x", 999, "Unknown host", "Helper plugin")
    step(pu, clock, "x", 1)
    assert pu.undo(LOGIC)[0]


def test_plugin_that_went_away_is_skipped():
    pu, clock = setup()
    hello(pu, "a", 200, "Avid Pro Tools", "A")
    hello(pu, "b", 200, "Avid Pro Tools", "B")
    step(pu, clock, "a", 1)
    step(pu, clock, "b", 1)
    pu.link.down.add("b")
    ok, said = pu.undo(PT)
    assert ok and said.startswith("Plugin undo: Gain") and said.endswith("· A")
    pu.link_closed("b")
    assert "b" not in pu.timeline.sources


def test_plugins_own_buttons_keep_the_timeline_in_step():
    pu, clock = setup()
    hello(pu, "a", 200, "Avid Pro Tools", "A")
    step(pu, clock, "a", 1)
    step(pu, clock, "a", 2)
    pu.link_message("a", {"op": "undone", "id": 2})      # clicked Undo in the plugin itself
    pu.link_message("a", {"op": "undone", "id": 2})      # echoes are harmless
    pu.undo(PT)
    assert pu.link.sent == [("a", "undo", 1)]
    pu.link_message("a", {"op": "sync", "undo": [{"id": 7, "label": "Mix", "age": 3}], "redo": []})
    assert pu.undo(PT)[1].startswith("Plugin undo: Mix")


def test_compare_is_undo_then_redo():
    pu, clock = setup()
    hello(pu, "a", 200, "Avid Pro Tools", "A")
    step(pu, clock, "a", 1, "Threshold")
    assert pu.compare(True, PT) == (True, "Before: Threshold")
    assert pu.compare(False, PT) == (True, "After")
    assert pu.link.sent == [("a", "undo", 1), ("a", "redo", 1)]
    assert pu.compare(False, PT) is None


def test_nothing_to_undo_says_how_to_get_it():
    pu, clock = setup()
    assert "Limitless Undo" in pu.undo(PT)[1]
    assert "in its window" in pu.undo(LOGIC)[1]


def test_logic_windows_and_linked_plugins_share_one_order():
    pu, clock = setup()
    clock.t += 1
    pu.window_touch("w1", 100, "Channel EQ")
    hello(pu, "lu", 100, "Apple Logic", "Serum", "Synth")
    step(pu, clock, "lu", 1, "Cutoff")      # comes 1 s after the click: a separate change
    clock.t += 1
    pu.window_touch("w2", 100, "Compressor")
    assert pu.undo(LOGIC) == (True, "Plugin undo in Compressor")
    assert pu.undo(LOGIC)[1].startswith("Plugin undo: Cutoff")
    assert pu.undo(LOGIC) == (True, "Plugin undo in Channel EQ")
    assert pu.windows.pressed == [("w2", "undo"), ("w1", "undo")]


def test_click_in_a_limitless_undo_window_isnt_counted_twice():
    pu, clock = setup()
    hello(pu, "lu", 100, "Apple Logic", "Serum")
    pu.window_touch("w1", 100, "Synth")
    clock.t += 0.3
    pu.link_message("lu", {"op": "step", "id": 1, "label": "Cutoff"})
    pu.undo(LOGIC)
    assert pu.undo(LOGIC)[0] is False
    assert pu.windows.pressed == []


def test_closed_logic_window_is_forgotten_and_the_next_one_undone():
    pu, clock = setup()
    pu.window_touch("w1", 100, "EQ")
    clock.t += 1
    pu.window_touch("w2", 100, "Comp")
    pu.windows.closed.add("w2")
    assert pu.undo(LOGIC) == (True, "Plugin undo in EQ")


def test_manual_undo_button_in_logic_window():
    pu, clock = setup()
    pu.window_touch("w1", 100, "EQ")
    pu.window_manual("w1", "undo")
    assert pu.undo(LOGIC)[0] is False
    assert pu.redo(LOGIC) == (True, "Plugin redo in EQ")


def test_front_window_undo():
    pu, clock = setup()
    assert pu.undo_front(PT)[0] is False
    assert pu.undo_front(LOGIC) == (False, "No plugin window is in front.")
    pu.windows.front_key = ("w9", "Space Designer")
    assert pu.undo_front(LOGIC) == (True, "Plugin undo in Space Designer")


def test_history_rows_newest_first():
    tl = Timeline(clock=Clock())
    tl.add_source("a", "link", plugin="A")
    tl.push("a", 1, "x", at=1)
    tl.push("a", 2, "y", at=2)
    tl.mark_undone("a", 2)
    rows = tl.recent()
    assert [(r[1].id, r[2]) for r in rows] == [(2, True), (1, False)]


# The real link, over a socket -------------------------------------------------------------

class PluginClient:
    """Speaks the link the way the Limitless Undo plugin does."""

    def __init__(self, info_path):
        info = json.loads(info_path.read_text())
        self.sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=3)
        self.token = info["token"]
        self.reader = self.sock.makefile("rb")

    def close(self):
        self.reader.close()
        self.sock.close()

    def send(self, **msg):
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def read(self):
        return json.loads(self.reader.readline())


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_link_server_end_to_end(tmp_path):
    pu = PluginUndo()
    server = LinkServer(tmp_path / "undo-link.json", pu.link_message, pu.link_closed, "test").start()
    pu.link = server
    try:
        info = json.loads((tmp_path / "undo-link.json").read_text())
        assert info["port"] == server.port and len(info["token"]) == 32

        bad = PluginClient(tmp_path / "undo-link.json")
        bad.send(op="hello", token="wrong", instance="x")
        assert bad.read()["op"] == "error"

        c = PluginClient(tmp_path / "undo-link.json")
        c.send(op="hello", token=c.token, instance="abc", host="Avid Pro Tools", pid=200,
               plugin="Pro-Q 3", track="Bass")
        assert c.read()["op"] == "welcome"
        c.send(op="step", id=1, label="Gain", before="0 dB", after="2 dB")
        assert wait_for(lambda: pu.timeline.next_undo(200, "protools")[0] is not None)
        ok, said = pu.undo(PT)
        assert ok and "Pro-Q 3 on Bass" in said
        assert c.read() == {"op": "undo", "id": 1}
        c.close()
        assert wait_for(lambda: "link:abc" not in pu.timeline.sources)
    finally:
        server.stop()
    assert not (tmp_path / "undo-link.json").exists()


# Logic plugin windows, with a stand-in for the Accessibility API ----------------------------

class El:
    def __init__(self, role, title="", subrole="", kids=(), enabled=True, value=None):
        self.a = {"AXRole": role, "AXTitle": title, "AXSubrole": subrole, "AXEnabled": enabled,
                  "AXValue": value}
        self.kids = list(kids)
        self.parent = None
        for k in self.kids:
            k.parent = self


class FakeAX:
    PRESSABLE = {"AXButton", "AXCheckBox"}

    def __init__(self, at, pid=100):
        self.at, self.pid, self.pressed = at, pid, []

    def attr(self, el, name, default=None):
        if name == "AXWindow":
            while el is not None and el.a["AXRole"] != "AXWindow":
                el = el.parent
            return el
        v = el.a.get(name)
        return default if v is None else v

    def walk(self, root, max_nodes=0, max_depth=0):
        stack = [root]
        while stack:
            el = stack.pop(0)
            yield el
            stack.extend(el.kids)

    def matches(self, el, wanted):
        return (el.a.get("AXTitle") or "").lower() == wanted.lower()

    def same(self, a, b):
        return a is b

    def element_at(self, x, y):
        return self.at.get((x, y))

    def pid_of(self, el):
        return self.pid

    def window_of(self, el):
        return self.attr(el, "AXWindow")

    def find_pressable(self, root, wanted, max_nodes=0):
        return next((e for e in self.walk(root) if e.a["AXRole"] in self.PRESSABLE
                     and self.matches(e, wanted)), None)

    def press(self, el):
        self.pressed.append(el.a["AXTitle"])
        return True

    def front_window(self, pid):
        return self.at.get("front")


def logic_scene():
    undo, redo = El("AXButton", "Undo"), El("AXButton", "Redo")
    knob = El("AXGroup")
    close = El("AXButton", subrole="AXCloseButton")
    plugin = El("AXWindow", "Bass", kids=[close, El("AXGroup", kids=[undo, redo, El("AXButton", "Compare")]), knob])
    main_knob = El("AXGroup")
    main = El("AXWindow", "Project", kids=[El("AXButton", "Undo"), El("AXButton", "Redo"), main_knob])
    wrapped_knob = El("AXGroup")
    wrapped = El("AXWindow", "Synth", kids=[El("AXButton", "Undo"), El("AXButton", "Redo"),
                                            El("AXButton", "Compare"),
                                            El("AXStaticText", value="Limitless Undo"), wrapped_knob])
    at = {(1, 1): knob, (2, 2): undo, (3, 3): main_knob, (4, 4): close, (5, 5): wrapped_knob,
          "front": plugin}
    return FakeAX(at), plugin


def test_logic_windows_tracks_touches_and_presses_undo():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: pid == 100)
    pu.windows = lw
    lw.handle(1, 1, "down")
    lw.handle(1, 1, "up")
    src, step_ = pu.timeline.next_undo(100, "logic")
    assert src.plugin == "Bass" and src.kind == "window"
    assert pu.undo(LOGIC) == (True, "Plugin undo in Bass")
    assert ax.pressed == ["Undo"]
    assert pu.redo(LOGIC) == (True, "Plugin redo in Bass")
    assert ax.pressed == ["Undo", "Redo"]


def test_logic_windows_ignores_main_window_chrome_and_limitless_undo():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: pid == 100)
    for xy in [(3, 3), (4, 4), (5, 5)]:
        lw.handle(*xy, "down")
        lw.handle(*xy, "up")
    assert pu.timeline.next_undo(100, "logic") == (None, None)


def test_logic_windows_sees_its_own_undo_button_clicked():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: pid == 100)
    lw.handle(1, 1, "down")
    lw.handle(1, 1, "up")
    lw.handle(2, 2, "down")
    lw.handle(2, 2, "up")
    assert pu.timeline.next_undo(100, "logic") == (None, None)
    assert pu.timeline.next_redo(100, "logic")[0] is not None


def test_logic_windows_scrolls_count_once_per_gesture():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: pid == 100)
    for t in (0.0, 0.1, 0.2, 0.3, 5.0):
        lw.handle(1, 1, "scroll", at=t)
    assert len(pu.timeline.sources["logic-window:1"].undo) == 2


def test_logic_windows_other_apps_are_ignored():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: False)
    lw.handle(1, 1, "down")
    lw.handle(1, 1, "up")
    assert pu.timeline.sources == {}


def test_logic_windows_threaded_queue():
    pu, clock = setup()
    ax, plugin = logic_scene()
    lw = LogicWindows(pu, ax, is_logic=lambda pid: True).start()
    lw.mouse(1, 1, "down")
    lw.mouse(1, 1, "up")
    assert wait_for(lambda: pu.timeline.next_undo()[0] is not None)


def test_link_server_handles_many_plugins_at_once(tmp_path):
    pu = PluginUndo()
    server = LinkServer(tmp_path / "undo-link.json", pu.link_message, pu.link_closed).start()
    pu.link = server
    clients = []
    try:
        def one(i):
            c = PluginClient(tmp_path / "undo-link.json")
            c.send(op="hello", token=c.token, instance=f"p{i}", host="Avid Pro Tools", pid=200, plugin=f"P{i}")
            c.read()
            c.send(op="step", id=1, label=f"Knob {i}")
            clients.append(c)

        threads = [threading.Thread(target=one, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert wait_for(lambda: sum(len(s.undo) for s in pu.timeline.sources.values()) == 12)
        for _ in range(12):
            assert pu.undo(PT)[0]
        assert pu.undo(PT)[0] is False
    finally:
        for c in clients:
            c.close()
        server.stop()
