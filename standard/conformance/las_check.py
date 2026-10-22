#!/usr/bin/env python3
"""Limitless Access Standard test kit.

Checks a product (an app, plugin, instrument or device bridge) against the levels in
standard/README.md and prints a pass or fail per level, plus a JSON report to submit.

  # Test against a private hub of its own (nothing else on the computer is touched):
  python3 las_check.py --tool myplugin --try-all
  #   then start your product with LIMITLESS_SOUND_HOME set to the folder it prints.

  # Or test a product already connected to the Limitless Sound hub on this computer:
  python3 las_check.py --live --tool zoom --try in,out

Standard library only. Needs shared/hub from this repository for the private hub.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

STANDARD = "0.1"
ACTION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
# An Adaptive product must honor at least these shared settings.
ADAPTIVE_MIN = {"textScale", "highContrast", "reduceMotion"}
REPLY_LIMIT = 3.0
LEVELS = ["connected", "adaptive", "hands-free", "co-designed"]


class Hub:
    """The hub's local web API: the same for a private test hub and the live one."""

    def __init__(self, port: int, token: str):
        self.base, self.token = f"http://127.0.0.1:{port}", token

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 6.0) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"X-Limitless-Token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def state(self) -> dict:
        return self.call("GET", "/api/state")

    def invoke(self, action: str, args: dict | None = None) -> dict:
        return self.call("POST", "/api/invoke", {"action": action, "args": args or {}})

    def prefs(self, prefs: dict) -> dict:
        return self.call("POST", "/api/prefs", {"prefs": prefs})["prefs"]


def start_private_hub(home: Path):
    """A hub of the kit's own, in its own folder and on free ports."""
    os.environ["LIMITLESS_SOUND_HOME"] = str(home)
    root = Path(__file__).resolve().parents[2] / "shared" / "hub"
    sys.path.insert(0, str(root))
    from limitless_hub.server import Hub as RealHub  # noqa: E402

    class Quiet:
        def say(self, text):
            pass

    hub = RealHub({}, port=0, http_port=0, speaker=Quiet(), persist=False).start()
    info = json.loads((home / "link.json").read_text())
    return hub, Hub(info["http"], info["token"])


def live_hub() -> Hub:
    from_env = os.environ.get("LIMITLESS_SOUND_HOME")
    if from_env:
        folder = Path(from_env)
    elif sys.platform == "darwin":
        folder = Path.home() / "Library" / "Application Support" / "Limitless Sound"
    elif sys.platform == "win32":
        folder = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Limitless Sound"
    else:
        folder = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Limitless Sound"
    info = json.loads((folder / "link.json").read_text())
    return Hub(info["http"], info["token"])


def test_prefs(current: dict) -> dict:
    """Settings that differ from the musician's on every key, so a product can't pass by standing still."""
    out = {}
    for k, v in current.items():
        if isinstance(v, bool):
            out[k] = not v
        elif k == "textScale":
            out[k] = 1.5 if v != 1.5 else 1.25
        elif k == "dwellMs":
            out[k] = 1200 if v != 1200 else 1000
        elif k == "scanMs":
            out[k] = 1500 if v != 1500 else 1800
    out.pop("speak", None)  # leave spoken feedback alone while testing
    out.pop("oneVoice", None)
    return out


def wait_for(cond, timeout: float, step: float = 0.2):
    end = time.time() + timeout
    while time.time() < end:
        value = cond()
        if value:
            return value
        time.sleep(step)
    return cond()


class Report:
    def __init__(self, tool: str):
        self.tool = tool
        self.checks: list[dict] = []

    def add(self, level: str, cid: str, ok: bool, what: str, detail: str = "") -> None:
        self.checks.append({"level": level, "id": cid, "ok": ok, "check": what, "detail": detail})
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {cid:4} {what}" + (f"\n             {detail}" if detail else ""))

    def level_ok(self, level: str) -> bool:
        mine = [c for c in self.checks if c["level"] == level]
        return bool(mine) and all(c["ok"] is True for c in mine)


def check(hub: Hub, args) -> Report:
    rep = Report(args.tool)
    tool = args.tool

    print(f"\nConnected (level 1): {tool} joins the open protocol and takes actions from any input")
    conn = wait_for(lambda: next((t for t in hub.state()["tools"] if t["id"] == tool and t["connected"]), None),
                    args.wait)
    rep.add("connected", "C1", bool(conn), "Connects and says hello",
            "" if conn else f"No product called '{tool}' connected within {args.wait:.0f} s.")
    if not conn:
        return rep
    snap = hub.state()
    shared_intents = set(snap.get("intents") or {})
    actions = [a for a in snap["actions"] if a.get("tool") == tool and a.get("live")]
    rep.add("connected", "C2", bool(actions), "Announces its actions", f"{len(actions)} actions")
    bad_ids = [a["id"] for a in actions if not ACTION_ID.match(a["id"].split(".", 1)[1])]
    bad_labels = [a["id"] for a in actions if not str(a.get("label", "")).strip() or len(a["label"]) > 60]
    bad_intents = [a["id"] for a in actions if a.get("intent") and a["intent"] not in shared_intents]
    rep.add("connected", "C3", not (bad_ids or bad_labels or bad_intents),
            "Every action has a short id, a plain label (60 characters at most) and only shared intents",
            "; ".join(x for x in [f"ids: {bad_ids}" if bad_ids else "", f"labels: {bad_labels}" if bad_labels else "",
                                  f"intents: {bad_intents}" if bad_intents else ""] if x))
    wanted = [a["id"] for a in actions] if args.try_all else [f"{tool}.{x}" for x in args.try_ids]
    if not wanted:
        rep.add("connected", "C4", False, "Answers every action within 3 seconds",
                "Not run: pass --try-all, or --try with the actions that are safe to trigger.")
    else:
        slow, silent, failed = [], [], []
        for action in wanted:
            started = time.time()
            r = hub.invoke(action)
            took = time.time() - started
            if took > REPLY_LIMIT or r.get("message") == "No answer.":
                slow.append(action)
            elif not r.get("ok") and not str(r.get("message", "")).strip():
                silent.append(action)
            elif not r.get("ok"):
                failed.append(f"{action}: {r.get('message')}")
        rep.add("connected", "C4", not slow and not silent,
                f"Answers every action within 3 seconds ({len(wanted)} tried)",
                "; ".join(x for x in [f"too slow: {slow}" if slow else "",
                                      f"refused without saying why: {silent}" if silent else "",
                                      f"refused (fine, with a reason): {failed}" if failed else ""] if x))

    print("\nAdaptive (level 2): honors the musician's shared settings")
    before = dict(hub.state()["prefs"])
    test = test_prefs(before)
    key = f"{tool}.prefs.applied"
    hub.prefs(test)

    def caught_up():
        value = hub.state()["states"].get(key)
        if isinstance(value, dict) and value and all(value[k] == test[k] for k in value if k in test):
            return value
        return None

    applied = wait_for(caught_up, REPLY_LIMIT)
    try:
        hub.prefs(before)
    except Exception:
        pass
    names = {k for k in (applied or {}) if k in test}
    rep.add("adaptive", "A1", bool(names), "Applies a settings change within 3 seconds and says so (state prefs.applied)",
            f"honors: {sorted(names)}" if names else
            "No prefs.applied state matching the new settings within 3 s. See standard/README.md, Adaptive.")
    rep.add("adaptive", "A2", ADAPTIVE_MIN <= names, "Honors text size, high contrast and reduced motion",
            f"missing: {sorted(ADAPTIVE_MIN - names)}" if names and not ADAPTIVE_MIN <= names else "")

    print("\nHands-free (level 3): finishes its core job with no hands")
    rep.add("hands-free", "H1", "hands-free" in args.attest or "co-designed" in args.attest,
            "Core job done start to finish with no hands (eyes, voice or one switch), attested",
            "Attest with --attest hands-free --evidence <video or notes link>." if "hands-free" not in args.attest else
            f"evidence: {args.evidence or 'none given'}")
    rep.add("hands-free", "H2", bool(args.evidence) or "hands-free" not in args.attest, "Evidence linked",
            args.evidence or "")

    print("\nCo-designed (level 4): tested with disabled musicians")
    rep.add("co-designed", "D1", "co-designed" in args.attest,
            "Tested on camera with disabled musicians, with their consent, attested",
            "Attest with --attest co-designed --evidence <session link>." if "co-designed" not in args.attest else "")
    return rep


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Limitless Access Standard test kit")
    p.add_argument("--tool", required=True, help="the product's tool id, as it says hello")
    p.add_argument("--live", action="store_true", help="use the Limitless Sound hub already running here")
    p.add_argument("--try", dest="try_ids", default="", help="comma-separated actions safe to trigger")
    p.add_argument("--try-all", action="store_true", help="trigger every action the product announces")
    p.add_argument("--wait", type=float, default=60, help="seconds to wait for the product to connect")
    p.add_argument("--attest", default="", help="comma-separated levels you attest to: hands-free, co-designed")
    p.add_argument("--evidence", default="", help="a link to video or notes backing the attestation")
    p.add_argument("--json", dest="json_out", help="write the report here")
    p.add_argument("--level", choices=LEVELS, default="connected", help="exit 0 only if this level passes")
    args = p.parse_args(argv)
    args.try_ids = [x.strip() for x in args.try_ids.split(",") if x.strip()]
    args.attest = {x.strip() for x in args.attest.split(",") if x.strip()}

    private = None
    if args.live:
        hub = live_hub()
    else:
        home = Path(tempfile.mkdtemp(prefix="las-"))
        private, hub = start_private_hub(home)
        print(f"Private test hub running. Start your product with:\n  LIMITLESS_SOUND_HOME={home}")
    try:
        rep = check(hub, args)
    finally:
        if private:
            private.stop()

    passed = [lvl for lvl in LEVELS if all(rep.level_ok(x) for x in LEVELS[:LEVELS.index(lvl) + 1])]
    top = passed[-1] if passed else None
    print(f"\nLimitless Access Standard {STANDARD}: {args.tool} "
          + (f"meets level {LEVELS.index(top) + 1}, {top.title()}." if top else "doesn't meet level 1 yet."))
    report = {"standard": STANDARD, "tool": args.tool, "level": top, "levels": passed, "checks": rep.checks,
              "evidence": args.evidence, "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"Report written to {args.json_out}")
    return 0 if args.level in passed else 1


if __name__ == "__main__":
    sys.exit(main())
