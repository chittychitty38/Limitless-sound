"""Small helpers over the macOS Accessibility API: reading what's on screen in
another app and pressing its menus and buttons, the way VoiceOver does.
Needs the Accessibility permission. Mac only; import it only on a Mac."""

import re

from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCopyElementAtPosition,
                                 AXUIElementCreateApplication, AXUIElementCreateSystemWide,
                                 AXUIElementGetPid, AXUIElementPerformAction,
                                 AXUIElementSetMessagingTimeout)
from CoreFoundation import CFEqual, CFHash

TIMEOUT = 0.5   # seconds to wait for an app that's busy before giving up
PRESSABLE = {"AXButton", "AXCheckBox", "AXRadioButton", "AXMenuButton", "AXPopUpButton"}


def app(pid):
    el = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(el, TIMEOUT)
    return el


def attr(el, name, default=None):
    try:
        err, value = AXUIElementCopyAttributeValue(el, name, None)
    except Exception:
        return default
    return value if err == 0 and value is not None else default


def children(el):
    return list(attr(el, "AXChildren", None) or [])


def press(el):
    try:
        return AXUIElementPerformAction(el, "AXPress") == 0
    except Exception:
        return False


def pid_of(el):
    try:
        err, pid = AXUIElementGetPid(el, None)
        return pid if err == 0 else None
    except Exception:
        return None


def same(a, b):
    try:
        return a is not None and b is not None and bool(CFEqual(a, b))
    except Exception:
        return False


def element_hash(el):
    try:
        return CFHash(el)
    except Exception:
        return id(el)


def element_at(x, y):
    sw = AXUIElementCreateSystemWide()
    AXUIElementSetMessagingTimeout(sw, TIMEOUT)
    try:
        err, el = AXUIElementCopyElementAtPosition(sw, float(x), float(y), None)
    except Exception:
        return None
    return el if err == 0 else None


def window_of(el):
    win = attr(el, "AXWindow")
    if win is not None:
        return win
    for _ in range(40):           # walk up until we reach the window
        if el is None or attr(el, "AXRole") == "AXWindow":
            return el
        el = attr(el, "AXParent")
    return None


def norm(text):
    text = str(text or "").replace("…", "...").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def names(el):
    """Every name an element goes by: its title, description, help and identifier."""
    out = []
    for a in ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier"):
        v = attr(el, a)
        if isinstance(v, str) and v.strip():
            out.append(norm(v))
    return out


def matches(el, wanted):
    """Exact name first; otherwise the name without a trailing '...'."""
    wanted = norm(wanted)
    loose = wanted.rstrip(". ")
    for n in names(el):
        if n == wanted or n.rstrip(". ") == loose:
            return True
    return False


def walk(root, max_nodes=2500, max_depth=30):
    """Every element under root, breadth first, up to a limit."""
    queue, seen = [(root, 0)], 0
    while queue and seen < max_nodes:
        el, depth = queue.pop(0)
        seen += 1
        yield el
        if depth < max_depth:
            queue.extend((c, depth + 1) for c in children(el))


def find_pressable(root, wanted, max_nodes=2500):
    for el in walk(root, max_nodes):
        if attr(el, "AXRole") in PRESSABLE and matches(el, wanted):
            return el
    return None


def front_window(pid):
    a = app(pid)
    return attr(a, "AXFocusedWindow") or attr(a, "AXMainWindow")


def press_menu(pid, path):
    """Choose Menu > Item (> Submenu item) in an app. Returns (ok, message)."""
    menubar = attr(app(pid), "AXMenuBar")
    if menubar is None:
        return False, "Can't see that app's menus. Is Accessibility allowed for Limitless Keys?"
    level = menubar
    for i, title in enumerate(path):
        items = children(level)
        if level is not menubar and len(items) == 1 and attr(items[0], "AXRole") == "AXMenu":
            items = children(items[0])
        found = next((it for it in items if matches(it, title)), None)
        if found is None:
            return False, f"Couldn't find {' › '.join(path[:i + 1])}."
        if i == len(path) - 1:
            if attr(found, "AXEnabled", True) is False:
                return False, f"{' › '.join(path)} is greyed out right now."
            return (True, "") if press(found) else (False, f"Couldn't choose {' › '.join(path)}.")
        sub = children(found)
        level = sub[0] if sub else found
    return False, "Couldn't find that menu item."


def press_button(pid, name):
    win = front_window(pid)
    if win is None:
        return False, "No window is in front."
    el = find_pressable(win, name)
    if el is None:
        return False, f"Couldn't find a {name} button in the window in front."
    if attr(el, "AXEnabled", True) is False:
        return False, f"The {name} button is greyed out."
    return (True, "") if press(el) else (False, f"Couldn't press {name}.")


def report(el, max_nodes=4000):
    """A text outline of everything in a window, to help make Limitless Keys work
    with an app it doesn't know yet."""
    lines = []

    def visit(e, depth):
        if len(lines) >= max_nodes:
            return
        role = attr(e, "AXRole", "?")
        sub = attr(e, "AXSubrole", "")
        bits = [f"{role}{'/' + sub if sub else ''}"]
        for a in ("AXTitle", "AXDescription", "AXHelp", "AXIdentifier", "AXValue"):
            v = attr(e, a)
            if isinstance(v, (str, int, float)) and str(v).strip():
                bits.append(f"{a[2:].lower()}={str(v)[:80]!r}")
        if attr(e, "AXEnabled") is False:
            bits.append("disabled")
        lines.append("  " * depth + " ".join(bits))
        if depth < 40:
            for c in children(e):
                visit(c, depth + 1)

    visit(el, 0)
    return "\n".join(lines)
