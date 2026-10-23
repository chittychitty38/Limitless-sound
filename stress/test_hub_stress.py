"""The Limitless Sound hub under load, on real sockets.

What a musician's suite does to the hub on a bad day: every app open and firing at
once, an app that hangs, apps crashing and reopening, garbage on the wire, links
that set each other off, and hours of uptime.
"""

from __future__ import annotations

import itertools
import json
import random
import socket
import threading
import time

import pytest

from conftest import Soak, need, percentile, rss_mb, wait_for

need("hub")

from limitless_hub.server import Hub  # noqa: E402
from limitless_link import Link  # noqa: E402

# Known hub bugs, fixed on the hub's own pull request. strict=True: once the fix lands these
# pass, the run turns red, and the marker must come off so they guard against regressions.

TOOLS = ["voice", "onehand", "zoom", "color", "control", "gaze"]
ACTIONS = [{"id": f"a{i}", "label": f"Action {i}"} for i in range(6)]


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text, lang="en"):
        self.said.append(text)


class SlowLauncher:
    """Zoom is installed but closed; its command line takes a while to answer, like a cold app launch."""

    def __init__(self, delay=1.5):
        self.delay = delay

    def find(self, tool):
        return "/Applications/Limitless Zoom.app" if tool == "zoom" else None

    def run_cli(self, tool, action, args):
        time.sleep(self.delay)
        return True, "ok"

    def open(self, tool):
        return {"ok": False, "message": "test"}

    def open_many(self, tools):
        return {"ok": False, "message": "test"}

    def open_settings(self):
        return {"ok": False, "message": "test"}


LIVE: list = []  # every Link a test starts, stopped after the test even when it fails


@pytest.fixture(autouse=True)
def stop_links():
    yield
    while LIVE:
        LIVE.pop().stop()


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    h = Hub({}, port=0, http_port=0, speaker=Speaker(), persist=False).start()
    yield h
    while LIVE:
        LIVE.pop().stop()
    h.stop()


def connect(tool_id, counter=None, delay=0.0, subscribe=None, on_event=None):
    def on_invoke(action, args, source):
        if delay:
            time.sleep(delay)
        if counter is not None:
            counter[tool_id] = counter.get(tool_id, 0) + 1
        return True, action

    link = Link(tool_id, tool_id.title(), "stress", actions=ACTIONS, on_invoke=on_invoke, retry=0.05,
                subscribe=subscribe, on_event=on_event).start()
    LIVE.append(link)
    assert wait_for(lambda: link.connected, 5), f"{tool_id} never connected"
    return link


def raw(hub, hello=True, tool="rawtool"):
    s = socket.create_connection(("127.0.0.1", hub.port), timeout=5)
    if hello:
        s.sendall((json.dumps({"op": "hello", "token": hub.token, "tool": tool, "actions": ACTIONS}) + "\n").encode())
        f = s.makefile("rb")
        assert json.loads(f.readline())["op"] == "welcome"
    return s


def timed_invokes(link, targets, count, timeout=10.0):
    """Fire `count` invokes as fast as possible; return (latencies, failures)."""
    lat, fails = [], []
    done = threading.Semaphore(0)
    for i in range(count):
        target = targets[i % len(targets)]
        t0 = time.perf_counter()

        def got(r, t0=t0):
            lat.append(time.perf_counter() - t0)
            if not r.get("ok"):
                fails.append(r)
            done.release()

        assert link.invoke(target, on_result=got)
    for _ in range(count):
        assert done.acquire(timeout=timeout), f"only {len(lat)} of {count} invokes were answered"
    return lat, fails


def test_every_app_firing_at_once(hub):
    """Six apps connected and invoking each other flat out, while a musician presses a switch.

    The flood is far beyond anything real (thousands of actions a second); what matters is
    that the musician's own press still lands quickly and nothing is lost.
    """
    counter: dict = {}
    links = [connect(t, counter) for t in TOOLS]
    results = {}

    def blast(link):
        targets = [f"{t}.a{i}" for t in TOOLS if t != link.tool for i in range(6)]
        for _ in range(10):
            lat, fails = timed_invokes(link, targets, 150)
            results.setdefault(link.tool, ([], []))
            results[link.tool][0].extend(lat)
            results[link.tool][1].extend(fails)

    threads = [threading.Thread(target=blast, args=(link,)) for link in links]
    musician = connect("switch")
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    presses = []
    while any(t.is_alive() for t in threads):
        lat, fails = timed_invokes(musician, ["zoom.a0"], 1)
        assert not fails
        presses += lat
        time.sleep(0.05)
    elapsed = time.perf_counter() - t0
    flood = [x for lat, _ in results.values() for x in lat]
    fails = [f for _, f in results.values() for f in f]
    print(f"\n{len(flood)} flood invokes in {elapsed:.1f}s ({len(flood)/elapsed:.0f}/s); "
          f"musician's {len(presses)} presses: p50 {percentile(presses, .5)*1000:.1f} ms, "
          f"p99 {percentile(presses, .99)*1000:.1f} ms, max {max(presses)*1000:.1f} ms")
    assert len(flood) == 6 * 1500
    assert not fails, fails[:3]
    assert sum(counter.values()) == 6 * 1500 + len(presses)
    # On a real Mac it is a few milliseconds. Here the hub and all seven apps share one Python
    # process pushing 9,000 invokes, and shared CI runners are sometimes 3x slower than usual
    # (p99 0.51-0.65 s seen). A press starved behind the flood would take seconds: still caught.
    assert percentile(presses, .99) < 1.0
    for link in links + [musician]:
        link.stop()


def test_a_hung_app_does_not_hold_up_the_others(hub):
    """One app freezes (beachball) and stops reading. Everyone else carries on."""
    stuck = raw(hub, tool="color")
    stuck.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    # The asking app doesn't listen to the flood itself: that case is the next test.
    a, b = connect("voice", subscribe=["zoom.connected"]), connect("zoom")
    # Bury the frozen app in events until its socket buffer and the hub's queue are full.
    for i in range(3000):
        b.state("keys", i)
    lat, fails = timed_invokes(a, ["zoom.a1"], 300)
    print(f"\nwith a frozen app: p99 {percentile(lat, .99)*1000:.1f} ms")
    assert not fails
    assert percentile(lat, .99) < 0.5
    # Invokes sent to the frozen app time out with a plain answer instead of hanging.
    box = {}
    a.invoke("color.a0", on_result=box.update)
    assert wait_for(lambda: box, 6), "an invoke to a frozen app never got an answer"
    assert box["ok"] is False
    stuck.close()
    a.stop()
    b.stop()


def test_answers_are_never_dropped_behind_a_burst_of_events(hub):
    """A slow app (an older Intel Mac, a busy Qt window) gets a burst of events, then asks for something.

    The hub keeps at most 1,000 messages waiting per app and drops the rest. It must drop
    events, never the answer to something the app asked for, or that app waits forever.
    """
    gate = threading.Event()
    slow = connect("voice", subscribe=["zoom.keys"], on_event=lambda n, v, s: gate.wait(60))
    noisy = connect("zoom")
    sent = itertools.count()
    flooding = threading.Event()
    flooding.set()

    def flood():
        while flooding.is_set():
            noisy.state("keys", f"{next(sent):07d}" + "x" * 400)

    flooder = threading.Thread(target=flood, daemon=True)
    flooder.start()
    # Far more than the operating system buffers between two apps, so the hub's own queue for
    # the busy app is full, and stays full while the events keep coming.
    assert wait_for(lambda: int(str(hub.bus.states.get("zoom.keys", "0"))[:7]) > 40000, 60)
    answered = []
    for _ in range(20):
        assert slow.invoke("zoom.a1", on_result=answered.append)
        time.sleep(0.05)
    time.sleep(0.5)
    flooding.clear()
    flooder.join()
    gate.set()                      # the app catches up
    assert wait_for(lambda: len(answered) == 20, 30), f"only {len(answered)} of 20 answers arrived"


def test_a_closed_app_launching_from_its_command_line_does_not_freeze_the_suite(tmp_path, monkeypatch):
    """Zoom is closed, so the hub runs it from its command line. That must not stall everyone else."""
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    h = Hub({}, port=0, http_port=0, speaker=Speaker(), launcher=SlowLauncher(1.5), persist=False).start()
    try:
        a, b = connect("voice"), connect("control")
        slow = threading.Thread(target=lambda: h.invoke_wait("zoom.in", {}, "test", timeout=5))
        slow.start()
        time.sleep(0.1)
        lat, fails = timed_invokes(a, ["control.a0"], 20)
        slow.join()
        print(f"\nwhile Zoom's command line runs: max {max(lat)*1000:.0f} ms")
        assert not fails
        assert max(lat) < 0.5, "the whole suite waited for one closed app's command line"
        a.stop()
        b.stop()
    finally:
        h.stop()


def test_apps_crashing_and_reopening(hub):
    """300 crash-and-reopen cycles, plus half-open connections that never say hello."""
    threads_before = threading.active_count()
    keeper = connect("voice")
    for i in range(300):
        s = raw(hub, tool=random.choice(TOOLS[1:]))
        if i % 3 == 0:
            s.shutdown(socket.SHUT_RDWR)  # crash mid-session
        s.close()
        if i % 10 == 0:
            socket.create_connection(("127.0.0.1", hub.port)).close()  # connects, says nothing
    assert wait_for(lambda: set(hub.bus.tools) == {"voice"}, 10), sorted(hub.bus.tools)
    lat, fails = timed_invokes(connect("zoom"), ["voice.a0"], 50)
    assert not fails
    # Every closed connection's reader and writer threads are gone.
    assert wait_for(lambda: threading.active_count() <= threads_before + 12, 10), threading.active_count()
    assert not hub.bus.pending
    keeper.stop()


def test_garbage_on_the_wire_never_takes_the_hub_down(hub):
    """Malformed, oversized and hostile messages, from connections that did and didn't say hello."""
    good = connect("voice")
    rng = random.Random(7)
    payloads = [
        b"\xff\xfe\x00garbage\n", b"{\n", b"[]\n", b"null\n", b"42\n", b'"hello"\n',
        b"x" * 70000 + b"\n",
        json.dumps({"op": "invoke", "action": 5, "args": [1, 2], "depth": "lots"}).encode() + b"\n",
        json.dumps({"op": "did", "action": {"a": 1}, "depth": None}).encode() + b"\n",
        json.dumps({"op": "state", "key": ["x"], "value": {"deep": [1] * 1000}}).encode() + b"\n",
        json.dumps({"op": "actions", "actions": [{"id": 1}, "x", {"id": "y" * 500, "phrases": 7}]}).encode() + b"\n",
        json.dumps({"op": "say", "text": "x" * 100000}).encode()[:60000] + b"\n",
        json.dumps({"op": "result", "id": [1], "ok": "maybe"}).encode() + b"\n",
    ]
    for i in range(200):
        hello = i % 2 == 0
        try:
            s = raw(hub, hello=hello, tool=f"fuzz{i % 5}")
            for _ in range(5):
                if rng.random() < 0.3:
                    s.sendall(bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 300))) + b"\n")
                else:
                    s.sendall(rng.choice(payloads))
            s.close()
        except OSError:
            pass  # the hub is allowed to hang up on garbage
    lat, fails = timed_invokes(connect("zoom"), ["voice.a1"], 100)
    assert not fails
    assert good.connected


def test_a_bad_depth_cannot_switch_off_the_loop_guard(hub):
    """A negative depth on a message must not let a chain of links run past the 4-step limit."""
    hits = {"voice": 0, "zoom": 0}

    def make(tool):
        def on_invoke(action, args, source):
            hits[tool] += 1
            link.did(action)
            return True, action
        link = Link(tool, tool, "x", actions=ACTIONS, on_invoke=on_invoke, retry=0.05).start()
        LIVE.append(link)
        return link

    v, z = make("voice"), make("zoom")
    assert wait_for(lambda: v.connected and z.connected)
    assert not hub.bus.set_routes([
        {"id": "ping", "name": "a", "when": {"event": "voice.a0"}, "do": [{"action": "zoom.a0"}], "on": True},
        {"id": "pong", "name": "b", "when": {"event": "zoom.a0"}, "do": [{"action": "voice.a0"}], "on": True},
    ])
    s = raw(hub, tool="evil")
    s.sendall((json.dumps({"op": "invoke", "action": "voice.a0", "depth": -1000}) + "\n").encode())
    time.sleep(2.0)
    total = hits["voice"] + hits["zoom"]
    print(f"\nlink chain ran {total} steps")
    assert total <= 6, f"a negative depth let a link loop run {total} steps"
    s.close()
    v.stop()
    z.stop()


def test_link_loops_switch_themselves_off(hub):
    """Two links that trigger each other, fed by an app that keeps reporting: the runaway guard pauses them."""
    v = connect("voice")
    z = connect("zoom")
    assert not hub.bus.set_routes([
        {"id": "ab", "name": "a to b", "when": {"event": "voice.a0"}, "do": [{"action": "zoom.a0"}], "on": True},
        {"id": "ba", "name": "b to a", "when": {"event": "zoom.a0"}, "do": [{"action": "voice.a0"}], "on": True},
    ])
    for _ in range(200):
        v.did("a0")
    assert wait_for(lambda: not all(r["on"] for r in hub.bus.settings["routes"]), 5), "the loop was never paused"
    lat, fails = timed_invokes(v, ["zoom.a2"], 50)
    assert not fails
    v.stop()
    z.stop()


def test_two_copies_of_one_app_do_not_fight(hub):
    """A musician double-clicks an app and two copies open. The suite settles on one, it doesn't flap."""
    first = connect("zoom")
    second = connect("zoom")
    flaps = []
    v = Link("voice", "Voice", "x", on_event=lambda n, val, src: flaps.append(val) if n == "zoom.connected" else None,
             retry=0.05).start()
    LIVE.append(v)
    assert wait_for(lambda: v.connected)
    for i in range(30):  # both copies carry on as normal, reporting what they do
        first.did("a0")
        second.did("a1")
        time.sleep(0.1)
    print(f"\nzoom.connected changed {len(flaps)} times in 3 s")
    assert len(flaps) <= 2, f"two copies kept knocking each other off the hub ({len(flaps)} reconnects in 3 s)"
    assert "zoom" in hub.bus.tools


def test_soak(hub):
    """Hours of a session squeezed into STRESS_SECONDS: steady traffic, apps coming and going, page polling."""
    import urllib.request

    links = {t: connect(t) for t in TOOLS[:4]}
    rng = random.Random(1)
    soak = Soak()
    url = f"http://127.0.0.1:{hub.http_port}/api/state?since=0"
    answered = {"n": 0}

    def step(n):
        tool = rng.choice(list(links))
        link = links[tool]
        op = rng.random()
        if op < 0.6:
            link.invoke(f"{rng.choice([t for t in links if t != tool])}.a{rng.randint(0, 5)}",
                        on_result=lambda r: answered.__setitem__("n", answered["n"] + 1))
        elif op < 0.8:
            link.did(f"a{rng.randint(0, 5)}", value=n)
        elif op < 0.95:
            link.state("mode", n % 2 == 0)
        elif op < 0.98:
            req = urllib.request.Request(url, headers={"X-Limitless-Token": hub.token})
            urllib.request.urlopen(req, timeout=5).read()
        else:
            link.stop()  # the app quits...
            LIVE.remove(link)  # (holding on to it here would look like the hub leaking)
            links[tool] = connect(tool)  # ...and the musician opens it again
        time.sleep(0.002)

    n = soak.run(step)
    mem, threads = soak.growth()
    print(f"\nhub soak: {n} operations, {answered['n']} answered. {soak.report()}")
    assert answered["n"] > n * 0.5
    assert mem < 30, f"memory kept growing: {soak.report()}"
    assert threads < 10, f"threads kept growing: {soak.report()}"
    assert len(hub.bus.pending) < 50
    for link in links.values():
        link.stop()
