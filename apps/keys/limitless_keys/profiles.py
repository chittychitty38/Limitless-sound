"""Shortcut profiles: which shortcut does what, in which app.

Saved as shortcuts.json, in plain JSON a musician can read, share and edit:

    {"version": 1,
     "apps": {
       "daws":   {"bindings": [{"keys": "alt+cmd+z", "do": {"plugin": "undo"}}]},
       "*":      {"bindings": []},
       "logic":  {"bindings": [{"keys": "f13", "do": {"menu": "Edit > Undo History…"}}]},
       "com.example.app": {"name": "Some App", "bindings": []}}}

A profile is one of the DAWs in daws.py, "daws" (every DAW), "*" (every app),
or any other app's bundle id. When a shortcut is pressed, the profile for the
app in front is checked first, then "daws" if it's a DAW, then "*".

What a shortcut does ("do") is one of:

    {"keys": "cmd+z"}                    press keys; "cmd+a, cmd+c" presses one after another
    {"menu": "Edit > Undo History…"}     choose a menu item in the app in front
    {"button": "Bounce"}                 press a button, by its name, in the front window
    {"plugin": "undo"}                   plugin undo: undo, redo, compare (hold to hear
                                         before), undoFront, redoFront, history
    {"suite": "zoom.in", "args": {}}     any Limitless Sound action, through the hub
    {"type": "Verse 2"}                  type text
    {"say": "Saved"}                     say something out loud
    {"wait": 0.25}                       wait (in steps)
    {"app": "cheatSheet"}                Limitless Keys itself: cheatSheet, pause, settings
    {"pass": true}                       let the app have this shortcut after all
    {"steps": [ ...any of the above... ]}
"""

import copy
import json
from pathlib import Path

from .daws import ALL_SCOPE, DAWS, DAWS_SCOPE, factory_use, find_daw, scope_name
from .keys import Combo, format_combo, parse_combo, parse_sequence

PLUGIN_ACTIONS = {
    "undo": "Undo the last plugin change",
    "redo": "Redo the last plugin change",
    "compare": "Hold to hear the sound before the last plugin change",
    "undoFront": "Undo in the plugin window in front",
    "redoFront": "Redo in the plugin window in front",
    "history": "Show the plugin change history",
}
APP_ACTIONS = {
    "cheatSheet": "Show my shortcuts for this app",
    "pause": "Pause or resume Limitless Keys",
    "settings": "Open my shortcuts",
}
ACTION_TYPES = ("keys", "menu", "button", "plugin", "suite", "type", "say", "wait", "app",
                "pass", "steps")

DEFAULT_SHORTCUTS = {
    "version": 1,
    "apps": {
        DAWS_SCOPE: {"bindings": [
            {"keys": "alt+cmd+z", "do": {"plugin": "undo"}, "repeat": True},
            {"keys": "shift+alt+cmd+z", "do": {"plugin": "redo"}, "repeat": True},
            {"keys": "ctrl+alt+cmd+z", "do": {"plugin": "compare"}},
            {"keys": "ctrl+alt+cmd+h", "do": {"plugin": "history"}},
            {"keys": "ctrl+alt+cmd+/", "do": {"app": "cheatSheet"}},
        ]},
        ALL_SCOPE: {"bindings": []},
    },
}


def menu_path(value):
    """'Edit > Undo History…' or ['Edit', 'Undo History…'] -> ['Edit', 'Undo History…']."""
    parts = value if isinstance(value, (list, tuple)) else str(value).split(">")
    parts = [str(p).strip() for p in parts if str(p).strip()]
    if len(parts) < 2:
        raise ValueError("a menu item needs the menu and the item, like Edit > Undo")
    return parts


def check_action(action, depth=0):
    """Returns None if the action is valid, otherwise a plain-language problem."""
    if not isinstance(action, dict) or not action:
        return "nothing to do"
    kinds = [k for k in action if k in ACTION_TYPES]
    if len(kinds) != 1:
        return "say exactly one thing to do"
    kind = kinds[0]
    value = action[kind]
    try:
        if kind == "keys":
            parse_sequence(value)
        elif kind == "menu":
            menu_path(value)
        elif kind in ("button", "type", "say", "suite"):
            if not isinstance(value, str) or not value.strip():
                return f"{kind} needs some text"
            if kind == "suite" and "." not in value:
                return "a suite action looks like zoom.in"
        elif kind == "plugin":
            if value not in PLUGIN_ACTIONS:
                return f"plugin can be {', '.join(PLUGIN_ACTIONS)}"
        elif kind == "app":
            if value not in APP_ACTIONS:
                return f"app can be {', '.join(APP_ACTIONS)}"
        elif kind == "wait":
            if not isinstance(value, (int, float)) or not 0 <= value <= 10:
                return "wait is a number of seconds, up to 10"
        elif kind == "pass":
            if value is not True:
                return "pass must be true"
        elif kind == "steps":
            if depth > 0:
                return "steps can't hold more steps"
            if not isinstance(value, list) or not value:
                return "steps needs a list of things to do"
            for i, step in enumerate(value, 1):
                problem = check_action(step, depth + 1)
                if problem:
                    return f"step {i}: {problem}"
    except ValueError as e:
        return str(e)
    return None


def describe(action):
    """What an action does, in plain words, for the settings window and speech."""
    if not isinstance(action, dict):
        return "Nothing"
    if "keys" in action:
        try:
            combos = parse_sequence(action["keys"])
        except ValueError:
            return f"Press {action['keys']}"
        return "Press " + ", then ".join(format_combo(c) for c in combos)
    if "menu" in action:
        try:
            return "Choose " + " › ".join(menu_path(action["menu"]))
        except ValueError:
            return "Choose a menu item"
    if "button" in action:
        return f"Press the {action['button']} button"
    if "plugin" in action:
        return PLUGIN_ACTIONS.get(action["plugin"], "Plugin undo")
    if "suite" in action:
        return f"Run {action['suite']}"
    if "type" in action:
        return f"Type “{action['type']}”"
    if "say" in action:
        return f"Say “{action['say']}”"
    if "wait" in action:
        return f"Wait {action['wait']} s"
    if "app" in action:
        return APP_ACTIONS.get(action["app"], action["app"])
    if action.get("pass"):
        return "Let the app have this shortcut"
    if "steps" in action:
        return "; ".join(describe(s) for s in action["steps"])
    return "Nothing"


class Binding:
    """One shortcut in one profile."""

    def __init__(self, scope, data):
        self.scope = scope
        self.data = data
        self.combo = parse_combo(data["keys"])
        self.action = data["do"]
        self.repeat = bool(data.get("repeat", False))
        self.hold = self.action.get("plugin") == "compare"
        self.passes = bool(self.action.get("pass"))
        self.label = data.get("label") or describe(self.action)

    def __repr__(self):
        return f"Binding({self.scope!r}, {str(self.combo)!r}, {self.action!r})"


class Profiles:
    """All shortcut profiles, ready for fast lookup from the keyboard thread."""

    def __init__(self, data=None, path=None):
        self.path = Path(path) if path else None
        self.problems = []
        self.data = copy.deepcopy(DEFAULT_SHORTCUTS)
        if data is not None:
            self.data = data
        self.compile()

    # Loading and saving --------------------------------------------------------

    @classmethod
    def load(cls, path):
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("apps"), dict):
                raise ValueError("not a shortcuts file")
        except FileNotFoundError:
            data = None
        except (OSError, ValueError):
            # Keep a broken file for the musician to fix, and start from the defaults.
            try:
                path.replace(path.with_suffix(".broken.json"))
            except OSError:
                pass
            data = None
        return cls(data, path)

    def save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def export_to(self, path):
        Path(path).write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_from(self, path, replace=False):
        """Adds (or with replace, swaps in) the profiles in a shared shortcuts file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("apps"), dict):
            raise ValueError("That isn't a Limitless Keys shortcuts file.")
        if replace:
            self.data = data
        else:
            for scope, prof in data["apps"].items():
                mine = self.data["apps"].setdefault(scope, {"bindings": []})
                if prof.get("name"):
                    mine.setdefault("name", prof["name"])
                for b in prof.get("bindings", []):
                    self._put(mine, b)
        self.compile()

    def restore_defaults(self):
        self.data = copy.deepcopy(DEFAULT_SHORTCUTS)
        self.compile()

    # Lookup -----------------------------------------------------------------

    def compile(self):
        """Builds the lookup tables. Bad bindings are skipped and listed in problems."""
        table, problems = {}, []
        for scope, prof in self.data.get("apps", {}).items():
            for i, b in enumerate(prof.get("bindings", [])):
                if b.get("on", True) is False:
                    continue
                try:
                    problem = check_action(b.get("do"))
                    if problem:
                        raise ValueError(problem)
                    binding = Binding(scope, b)
                except (KeyError, TypeError, ValueError) as e:
                    problems.append(f"{scope_name(scope)}, shortcut {i + 1}: {e}")
                    continue
                table.setdefault(scope, {})[binding.combo] = binding
        # Swapped in whole, so the keyboard thread always sees one consistent table.
        self._table = table
        self.problems = problems

    def scopes_for(self, app_id):
        out = []
        if app_id:
            out.append(app_id)
        daw = find_daw(app_id)
        if daw:
            out += [daw, DAWS_SCOPE]
        out.append(ALL_SCOPE)
        return out

    def find(self, app_id, combo):
        table = self._table
        for scope in self.scopes_for(app_id):
            b = table.get(scope, {}).get(combo)
            if b is not None:
                return b
        return None

    def find_in_scope(self, scope, combo):
        """The binding for these keys in exactly this profile, if there is one."""
        return self._table.get(scope, {}).get(parse_combo(combo))

    def active(self, app_id):
        """Every shortcut that works in this app right now, most specific first."""
        table = self._table
        seen, out = set(), []
        for scope in self.scopes_for(app_id):
            for combo, b in table.get(scope, {}).items():
                if combo not in seen:
                    seen.add(combo)
                    if not b.passes:
                        out.append(b)
        return out

    # Editing ------------------------------------------------------------------

    def scopes(self):
        """Profiles to show, in a sensible order: every DAW, every app, then each app."""
        apps = self.data.setdefault("apps", {})
        fixed = [DAWS_SCOPE, ALL_SCOPE] + [k for k in DAWS if k in apps]
        return fixed + sorted(k for k in apps if k not in fixed)

    def name(self, scope):
        return self.data.get("apps", {}).get(scope, {}).get("name") or scope_name(scope)

    def bindings(self, scope):
        return self.data.setdefault("apps", {}).setdefault(scope, {"bindings": []})["bindings"]

    def add_scope(self, scope, name=None):
        prof = self.data.setdefault("apps", {}).setdefault(scope, {"bindings": []})
        if name and scope not in DAWS:
            prof["name"] = name
        return scope

    def remove_scope(self, scope):
        if scope not in (DAWS_SCOPE, ALL_SCOPE):
            self.data.get("apps", {}).pop(scope, None)
            self.compile()

    def _put(self, prof, binding):
        combo = parse_combo(binding["keys"])
        prof["bindings"] = [b for b in prof.get("bindings", [])
                            if _safe_combo(b.get("keys")) != combo]
        prof["bindings"].append(binding)

    def set_binding(self, scope, binding, replacing=None):
        """Adds a binding to a profile, replacing any other binding for the same keys."""
        problem = check_action(binding.get("do"))
        if problem:
            raise ValueError(problem)
        combo = parse_combo(binding["keys"])
        binding = dict(binding, keys=str(combo))
        prof = self.data.setdefault("apps", {}).setdefault(scope, {"bindings": []})
        if replacing is not None:
            old = _safe_combo(replacing)
            prof["bindings"] = [b for b in prof.get("bindings", []) if _safe_combo(b.get("keys")) != old]
        self._put(prof, binding)
        self.compile()

    def remove_binding(self, scope, keys):
        combo = _safe_combo(keys)
        prof = self.data.get("apps", {}).get(scope)
        if prof:
            prof["bindings"] = [b for b in prof.get("bindings", []) if _safe_combo(b.get("keys")) != combo]
            self.compile()

    def notes_for(self, scope, keys):
        """Warnings to show before saving a shortcut: what it replaces or hides."""
        combo = parse_combo(keys)
        notes = []
        for what, names in factory_use(scope, str(combo)).items():
            notes.append(f"Replaces {what} in {', '.join(names)}.")
        if combo.mods <= {"shift"} and len(combo.key) == 1:
            notes.append("A plain key stops you typing that letter in this app.")
        if combo in (parse_combo("cmd+q"), parse_combo("cmd+tab"), parse_combo("cmd+space")):
            notes.append("macOS uses this shortcut itself.")
        return notes


def _safe_combo(keys):
    try:
        return parse_combo(keys)
    except (ValueError, TypeError):
        return None


def binding_text(b):
    return f"{format_combo(b.combo)}  {b.label}"


__all__ = ["Profiles", "Binding", "check_action", "describe", "menu_path", "PLUGIN_ACTIONS",
           "APP_ACTIONS", "DEFAULT_SHORTCUTS", "Combo", "binding_text"]
