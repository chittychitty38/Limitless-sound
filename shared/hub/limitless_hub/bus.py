"""The action bus: every tool's actions in one place, any input can trigger any of them.

This module has no sockets in it. The server hands it messages and a `send`
function per connection, so all of the suite's behavior is tested directly.

Messages from a tool (one JSON object each):
  hello   {"tool", "name", "version", "token", "actions": [...], "subscribe": [...]}
  invoke  {"action": "zoom.in" | "daw.record", "args": {}, "id": n}   ask another tool to act
  did     {"action": "record", "intent": "daw.record", "value": ...}  "I just did this"
  state   {"key": "mode", "value": true}                              "my state changed"
  say     {"text": "Record"}                                          speak, one voice for the suite
  result  {"id": n, "ok": true, "message": "Zoomed in"}               answer to a hub invoke
Messages to a tool: welcome, invoke, event, prefs, actions, result, error.
"""

from __future__ import annotations

import itertools
import re
import threading
import time
from collections import deque
from fnmatch import fnmatchcase
from typing import Callable, Optional

from . import catalog, routes as routes_mod, setup as setup_mod

PROTOCOL = 1
TOOL_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_DEPTH = 4            # a link may start a link, but not forever
REPLY_TIMEOUT = 3.0      # seconds a tool has to answer an invoke

DEFAULT_PREFS = {
    "speak": True,          # spoken feedback from every tool
    "oneVoice": True,       # tools speak through the hub so they never talk over each other
    "textScale": 1.0,       # 1.0 to 2.0, for every window in the suite
    "highContrast": False,
    "reduceMotion": False,
    "dwellMs": 800,         # dwell time for eye, head and pointer selection
    "scanMs": 1200,         # switch scanning speed
}


STATE_LABELS = {
    "voice.listening": "Voice listening", "onehand.mode": "One-hand mode", "onehand.hand": "One-Hand hand",
    "zoom.keys": "Zoom keys", "color.filter": "Screen colors", "control.enabled": "Controller on/off",
    "control.layer": "Controller layer", "gaze.tracking": "Eye tracking", "hub.speaking": "Speaking",
    "app.front": "App in front", "app.daw": "DAW in front",
}


def _clean_text(v, limit=500) -> str:
    return str(v if v is not None else "")[:limit]


def _depth(msg: dict) -> int:
    """How many links led here, as an app reports it: trusted only within 0..MAX_DEPTH+1."""
    d = msg.get("depth")
    if isinstance(d, bool) or not isinstance(d, int):
        return 0
    return min(max(d, 0), MAX_DEPTH + 1)


class Conn:
    """One connection: a tool, or the settings page / command line acting for the musician."""

    def __init__(self, send: Callable[[dict], None], kind: str = "app"):
        self.send = send
        self.kind = kind
        self.tool: Optional[str] = None
        self.name = ""
        self.version = ""
        self.actions: dict[str, dict] = {}
        self.subscribe: list[str] = ["*"]
        self.connected_at = time.time()
        self.closed = False

    def wants(self, event: str) -> bool:
        return any(fnmatchcase(event, p) for p in self.subscribe)


class Bus:
    def __init__(self, settings: dict, token: str, *, speaker=None, launcher=None,
                 save: Callable[[dict], None] | None = None, clock=time.monotonic,
                 background: Callable[[Callable[[], None]], None] | None = None):
        self.lock = threading.RLock()
        # Slow work (a closed app's command line) runs here, never while holding the lock.
        self.background = background or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self.token = token
        self.speaker = speaker
        self.launcher = launcher
        self.save = save or (lambda s: None)
        self.clock = clock
        self.settings = settings
        settings.setdefault("routes", [dict(r) for r in routes_mod.DEFAULT_ROUTES])
        settings["prefs"] = {**DEFAULT_PREFS, **settings.get("prefs", {})}
        settings.setdefault("intentOrder", list(catalog.DEFAULT_INTENT_ORDER))
        self.tools: dict[str, Conn] = {}
        self.states: dict[str, object] = {}
        self.pending: dict[int, tuple[Callable[[dict], None], float]] = {}
        self.ids = itertools.count(1)
        self.log_seq = itertools.count(1)
        self.log: deque[dict] = deque(maxlen=300)
        self.guard = routes_mod.RunawayGuard(clock)

    # ---------------------------------------------------------------- connections

    def attach(self, send: Callable[[dict], None], kind: str = "app") -> Conn:
        return Conn(send, kind)

    def detach(self, conn: Conn) -> None:
        with self.lock:
            conn.closed = True
            if conn.tool and self.tools.get(conn.tool) is conn:
                del self.tools[conn.tool]
                self._note(f"{conn.name or conn.tool} closed", "tool")
                self.emit(f"{conn.tool}.connected", False, source="hub")
                self._broadcast_actions()

    def receive(self, conn: Conn, msg: dict) -> bool:
        """Handle one message. Returns False when the connection should be closed."""
        if not isinstance(msg, dict):
            return True
        op = msg.get("op")
        with self.lock:
            if conn.tool is None and conn.kind == "app":
                if op != "hello":
                    conn.send({"op": "error", "message": "Say hello first."})
                    return False
                return self._hello(conn, msg)
            if op == "invoke":
                self._invoke_from(conn, msg)
            elif op == "did":
                self._did(conn, msg)
            elif op == "state":
                self._state(conn, msg)
            elif op == "say":
                self.say(_clean_text(msg.get("text")), source=conn.tool or "hub")
            elif op == "result":
                self._result(msg)
            elif op == "actions":
                conn.actions = self._parse_actions(msg.get("actions"))
                self._broadcast_actions()
            elif op == "ping":
                conn.send({"op": "pong"})
            elif op == "hello":
                pass
            else:
                conn.send({"op": "error", "message": f"Unknown op {op!r}."})
        return True

    def _parse_actions(self, raw) -> dict[str, dict]:
        out = {}
        for a in raw or []:
            if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not a["id"]:
                continue
            item = {"id": a["id"][:64], "label": _clean_text(a.get("label") or a["id"], 120)}
            if isinstance(a.get("intent"), str) and a["intent"] in catalog.INTENTS:
                item["intent"] = a["intent"]
            if isinstance(a.get("phrases"), list):
                item["phrases"] = [_clean_text(p, 80) for p in a["phrases"][:12]]
            if isinstance(a.get("args"), dict):
                item["args"] = {str(k)[:32]: str(v)[:16] for k, v in a["args"].items()}
            out[item["id"]] = item
        return out

    def _hello(self, conn: Conn, msg: dict) -> bool:
        if msg.get("token") != self.token:
            conn.send({"op": "error", "message": "Wrong token. Read link.json again."})
            return False
        tool = msg.get("tool")
        if not isinstance(tool, str) or not TOOL_ID.match(tool) or tool in ("hub", "daw", "app"):
            conn.send({"op": "error", "message": "Tool id must be short, lowercase letters and digits."})
            return False
        conn.tool = tool
        conn.name = _clean_text(msg.get("name") or catalog.TOOLS.get(tool, {}).get("name") or tool, 60)
        conn.version = _clean_text(msg.get("version"), 30)
        conn.actions = self._parse_actions(msg.get("actions"))
        subs = msg.get("subscribe")
        if isinstance(subs, list):
            conn.subscribe = [str(s)[:64] for s in subs[:32]]
        old = self.tools.get(tool)
        if old is not None and old is not conn:
            old.closed = True
            # The newest copy wins; clients stop reconnecting on "replaced" so two copies don't fight.
            old.send({"op": "error", "code": "replaced",
                      "message": "Another copy of this app connected; closing this one."})
        self.tools[tool] = conn
        conn.send({
            "op": "welcome", "protocol": PROTOCOL, "prefs": self.settings["prefs"],
            "actions": self.all_actions(), "states": dict(self.states),
            "tools": sorted(self.tools),
        })
        self._note(f"{conn.name} connected", "tool")
        self.emit(f"{tool}.connected", True, source="hub")
        self._broadcast_actions(skip=conn)
        return True

    # ---------------------------------------------------------------- actions

    def all_actions(self) -> list[dict]:
        """Every action in the suite, live ones first, plus the hub's and the shared DAW intents."""
        out = []
        seen = set()
        for tool, conn in sorted(self.tools.items()):
            for a in conn.actions.values():
                out.append({**a, "id": f"{tool}.{a['id']}", "tool": tool, "live": True})
                seen.add(tool)
        for tool, spec in catalog.TOOLS.items():
            if tool in seen:
                continue
            for a in spec["actions"]:
                out.append({**a, "id": f"{tool}.{a['id']}", "tool": tool, "live": False})
        for a in catalog.HUB_ACTIONS:
            out.append({**a, "id": f"hub.{a['id']}", "tool": "hub", "live": True})
        for intent, label in catalog.INTENTS.items():
            out.append({"id": intent, "label": label, "tool": "daw", "live": bool(self._providers(intent))})
        return out

    def known_action_ids(self) -> set[str]:
        return {a["id"] for a in self.all_actions()}

    def _broadcast_actions(self, skip: Conn | None = None) -> None:
        msg = {"op": "actions", "actions": self.all_actions(), "tools": sorted(self.tools)}
        for conn in list(self.tools.values()):
            if conn is not skip:
                conn.send(msg)

    def _providers(self, intent: str) -> list[tuple[str, str]]:
        order = self.settings.get("intentOrder") or catalog.DEFAULT_INTENT_ORDER
        rank = {t: i for i, t in enumerate(order)}
        found = []
        for tool, conn in self.tools.items():
            for a in conn.actions.values():
                if a.get("intent") == intent:
                    found.append((tool, a["id"]))
                    break
        return sorted(found, key=lambda p: rank.get(p[0], len(rank)))

    def label_for(self, action: str) -> str:
        if action in STATE_LABELS:
            return STATE_LABELS[action]
        tool, _, act = action.partition(".")
        if tool == "daw":
            return catalog.INTENTS.get(action, action)
        conn = self.tools.get(tool)
        if conn and act in conn.actions:
            return conn.actions[act]["label"]
        for a in catalog.TOOLS.get(tool, {}).get("actions", []) + (catalog.HUB_ACTIONS if tool == "hub" else []):
            if a["id"] == act:
                return a["label"]
        return action

    def _invoke_from(self, conn: Conn, msg: dict) -> None:
        req_id = msg.get("id")

        def reply(result: dict) -> None:
            if req_id is not None:
                conn.send({"op": "result", "id": req_id, **result})

        self.invoke(str(msg.get("action") or ""), msg.get("args") if isinstance(msg.get("args"), dict) else {},
                    source=conn.tool or conn.kind, depth=_depth(msg), on_result=reply)

    def invoke(self, action: str, args: dict | None = None, *, source: str = "hub", depth: int = 0,
               on_result: Callable[[dict], None] | None = None) -> None:
        """Run any action in the suite. The answer comes to on_result (now or a little later)."""
        done = on_result or (lambda r: None)
        args = args or {}
        with self.lock:
            if depth > MAX_DEPTH:
                self._note(f"Stopped a chain of links at {action}: too many steps", "warn")
                return done({"ok": False, "message": "Too many linked steps."})
            tool, _, act = action.partition(".")
            if not tool or not act:
                return done({"ok": False, "message": f"'{action}' isn't an action. Try something like zoom.in."})
            if tool == "hub":
                return done(self._hub_action(act, args, source))
            if tool == "daw":
                providers = self._providers(action)
                if not providers:
                    via = self._intent_fallback(action)
                    if via:
                        return self.invoke(via, args, source=source, depth=depth, on_result=done)
                    label = catalog.INTENTS.get(action, action)
                    msg = f"Nothing that can do “{label}” is open. Open Limitless Control or Limitless Voice."
                    self._note(msg, "warn")
                    return done({"ok": False, "message": msg})
                if len(providers) > 1:
                    return self._invoke_chain(action, providers, args, source, depth, done, [])
                tool, act = providers[0]
            conn = self.tools.get(tool)
            if conn is not None:
                if conn.actions and act not in conn.actions:
                    return done({"ok": False, "message": f"{conn.name} has no action '{act}'."})
                rid = next(self.ids)
                self.pending[rid] = (done, self.clock() + REPLY_TIMEOUT)
                conn.send({"op": "invoke", "id": rid, "action": act, "args": args,
                           "source": source, "depth": depth})
                self._note(f"{self._who(source)} → {conn.name}: {self.label_for(f'{tool}.{act}')}", "action")
                return
            return self._offline(tool, act, args, source, depth, done)

    def _invoke_chain(self, intent, providers, args, source, depth, done, failures) -> None:
        """Ask each app that can do an intent in turn, until one manages it
        (the controller may have no key for it in the app in front, but Voice does)."""
        if not providers:
            return done({"ok": False, "message": " ".join(failures) or "Nobody could do that."})
        tool, act = providers[0]

        def next_or_done(result: dict) -> None:
            if result.get("ok"):
                return done(result)
            with self.lock:
                self._invoke_chain(intent, providers[1:], args, source, depth, done,
                                   failures + [result.get("message") or ""])

        self.invoke(f"{tool}.{act}", args, source=source, depth=depth, on_result=next_or_done)

    def _intent_fallback(self, intent: str) -> str | None:
        """A closed tool with a command line can still answer some intents (zoom)."""
        for tool in self.settings.get("intentOrder") or catalog.DEFAULT_INTENT_ORDER:
            spec = catalog.TOOLS.get(tool)
            if not spec or not spec.get("cli"):
                continue
            for a in spec["actions"]:
                if a.get("intent") == intent and self.launcher and self.launcher.find(tool):
                    return f"{tool}.{a['id']}"
        return None

    def _offline(self, tool: str, act: str, args: dict, source: str, depth: int,
                 done: Callable[[dict], None]) -> None:
        spec = catalog.TOOLS.get(tool)
        if spec is None:
            return done({"ok": False, "message": f"No tool called '{tool}' is connected."})
        if self.launcher is None or not self.launcher.find(tool):
            msg = f"{spec['name']} isn't installed on this computer."
            self._note(msg, "warn")
            return done({"ok": False, "message": msg})

        def run() -> None:
            # A command line can take seconds; the rest of the suite keeps moving meanwhile.
            ok, message = self.launcher.run_cli(tool, act, args)
            with self.lock:
                if ok:
                    self._note(f"{self._who(source)} → {spec['name']}: {self.label_for(f'{tool}.{act}')}", "action")
                    # The tool can't report back over its command line, so the hub reports for it.
                    self._emit_did(tool, act, self._catalog_intent(tool, act), args or None, source, depth)
                    result = {"ok": True, "message": message}
                else:
                    msg = f"{spec['name']} isn't open. {message}".strip()
                    self._note(msg, "warn")
                    result = {"ok": False, "message": msg}
            done(result)

        self.background(run)

    def _catalog_intent(self, tool: str, act: str) -> str | None:
        for a in catalog.TOOLS.get(tool, {}).get("actions", []):
            if a["id"] == act:
                return a.get("intent")
        return None

    def _result(self, msg: dict) -> None:
        entry = self.pending.pop(msg.get("id"), None)
        if entry:
            ok = bool(msg.get("ok", True))
            entry[0]({"ok": ok, "message": _clean_text(msg.get("message"), 300)})

    def tick(self) -> None:
        """Answer invokes that a tool never replied to."""
        with self.lock:
            now = self.clock()
            for rid, (done, deadline) in list(self.pending.items()):
                if now > deadline:
                    del self.pending[rid]
                    done({"ok": False, "message": "The tool didn't answer in time."})

    def _hub_action(self, act: str, args: dict, source: str) -> dict:
        if act == "say":
            self.say(_clean_text(args.get("text")), source=source)
            return {"ok": True, "message": "Said it"}
        if act == "status":
            names = [c.name for c in self.tools.values()]
            text = ("Open: " + ", ".join(names)) if names else "No Limitless Sound tools are open."
            self.say(text, source="hub")
            return {"ok": True, "message": text}
        if act in ("open", "openAll", "settings"):
            if self.launcher is None:
                return {"ok": False, "message": "Opening tools isn't available here."}
            if act == "settings":
                return self.launcher.open_settings()
            if act == "openAll":
                return self.launcher.open_many(self.settings.get("startTools") or list(catalog.TOOLS))
            tool = str(args.get("tool") or "")
            if tool not in catalog.TOOLS:
                return {"ok": False, "message": f"Unknown tool '{tool}'."}
            return self.launcher.open(tool)
        return {"ok": False, "message": f"The hub has no action '{act}'."}

    # ---------------------------------------------------------------- events & links

    def _did(self, conn: Conn, msg: dict) -> None:
        act = str(msg.get("action") or "")[:64]
        if not act:
            return
        intent = msg.get("intent")
        if intent is None and act in conn.actions:
            intent = conn.actions[act].get("intent")
        self._emit_did(conn.tool, act, intent if intent in catalog.INTENTS else None,
                       msg.get("value"), conn.tool, _depth(msg))

    def _emit_did(self, tool, act, intent, value, source, depth) -> None:
        self.emit(f"{tool}.{act}", value, source=source, depth=depth)
        if intent:
            self.emit(intent, {"by": tool, "action": act}, source=source, depth=depth)

    def _state(self, conn: Conn, msg: dict) -> None:
        key = str(msg.get("key") or "")[:64]
        if not key:
            return
        # "app.*" states are shared (the app in front); anything else belongs to the sender.
        name = key if key.startswith("app.") else f"{conn.tool}.{key}"
        value = msg.get("value")
        if self.states.get(name, object()) == value:
            return
        self.states[name] = value
        self.emit(name, value, source=conn.tool, depth=_depth(msg))

    def set_state(self, name: str, value) -> None:
        with self.lock:
            if self.states.get(name, object()) == value:
                return
            self.states[name] = value
            self.emit(name, value, source="hub")

    def emit(self, name: str, value=None, *, source: str = "hub", depth: int = 0) -> None:
        with self.lock:
            msg = {"op": "event", "name": name, "value": value, "source": source}
            for tool, conn in list(self.tools.items()):
                if tool != source and conn.wants(name):
                    conn.send(msg)
            for route in self.settings.get("routes", []):
                if not routes_mod.matches(route, name, value):
                    continue
                if not self.guard.allow(route["id"]):
                    route["on"] = False
                    self.save(self.settings)
                    self._note(f"Paused the link “{route.get('name', route['id'])}”: it kept setting itself off.", "warn")
                    continue
                for step in route.get("do", []):
                    target = step["action"].partition(".")[0]
                    if target in catalog.TOOLS and target not in self.tools:
                        cli = catalog.TOOLS[target].get("cli") or {}
                        act = step["action"].partition(".")[2]
                        if not ((act in cli or "*" in cli) and self.launcher and self.launcher.find(target)):
                            continue  # a link to an app that's closed simply waits for it
                    self._note(f"Link: {self.label_for(name)} → {self.label_for(step['action'])}", "link")
                    self.invoke(step["action"], step.get("args") or {}, source=f"link:{route['id']}", depth=depth + 1)

    # ---------------------------------------------------------------- speech, prefs, settings

    def say(self, text: str, source: str = "hub") -> None:
        if not text or not self.settings["prefs"].get("speak", True):
            return
        if self.speaker is not None:
            self.speaker.say(text)

    def set_prefs(self, changes: dict) -> dict:
        with self.lock:
            prefs = self.settings["prefs"]
            for k, v in (changes or {}).items():
                if k not in DEFAULT_PREFS:
                    continue
                default = DEFAULT_PREFS[k]
                if isinstance(default, bool):
                    prefs[k] = bool(v)
                elif isinstance(default, (int, float)):
                    try:
                        num = float(v)
                    except (TypeError, ValueError):
                        continue
                    lo, hi = {"textScale": (1.0, 2.0), "dwellMs": (250, 3000), "scanMs": (400, 5000)}.get(k, (0, 1e9))
                    num = min(max(num, lo), hi)
                    prefs[k] = int(num) if isinstance(default, int) else round(num, 2)
            self.save(self.settings)
            for conn in self.tools.values():
                conn.send({"op": "prefs", "prefs": prefs})
            return prefs

    def set_routes(self, new_routes: list) -> list[str]:
        with self.lock:
            if not isinstance(new_routes, list):
                return ["Links must be a list."]
            known = self.known_action_ids()
            problems = []
            seen = set()
            for r in new_routes:
                problems += routes_mod.validate(r, known)
                if isinstance(r, dict):
                    if r.get("id") in seen:
                        problems.append(f"Two links share the id {r.get('id')}.")
                    seen.add(r.get("id"))
            if problems:
                return problems
            self.settings["routes"] = new_routes
            self.save(self.settings)
            return []

    def set_intent_order(self, order: list) -> None:
        with self.lock:
            clean = [t for t in order if isinstance(t, str) and TOOL_ID.match(t)]
            self.settings["intentOrder"] = clean
            self.save(self.settings)

    # ---------------------------------------------------------------- activity log

    def _who(self, source: str) -> str:
        if source.startswith("link:"):
            return "Link"
        if source in self.tools:
            return self.tools[source].name
        if source in catalog.TOOLS:
            return catalog.TOOLS[source]["name"]
        return {"hub": "Limitless Sound", "page": "Settings page", "cli": "Command line", "http": "Shortcut"}.get(source, source)

    def _note(self, text: str, kind: str = "info") -> None:
        self.log.append({"seq": next(self.log_seq), "time": time.time(), "text": text, "kind": kind})

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            tools = []
            for tool, spec in catalog.TOOLS.items():
                conn = self.tools.get(tool)
                path = self.launcher.find(tool) if self.launcher else None
                tools.append({"id": tool, "name": spec["name"], "about": spec["about"],
                              "connected": conn is not None, "installed": bool(path) or conn is not None,
                              "version": conn.version if conn else "",
                              "actions": len(conn.actions) if conn else len(spec["actions"])})
            for tool, conn in self.tools.items():
                if tool not in catalog.TOOLS:
                    tools.append({"id": tool, "name": conn.name, "about": "", "connected": True,
                                  "installed": True, "version": conn.version, "actions": len(conn.actions)})
            return {
                "tools": tools, "actions": self.all_actions(), "intents": catalog.INTENTS,
                "routes": self.settings["routes"], "prefs": self.settings["prefs"],
                "intentOrder": self.settings["intentOrder"], "states": dict(self.states),
                "startTools": self.settings.get("startTools", []),
                "setupDone": bool(self.settings.get("setupDone")),
                "setupInputs": self.settings.get("setupInputs", []),
                "setupChoices": setup_mod.choices(),
                "autostart": bool(self.settings.get("autostart")),
                "log": [e for e in self.log if e["seq"] > since],
            }
