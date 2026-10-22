#!/usr/bin/env python3
"""Proof that the suite a musician downloads really works.

Run it on a fresh computer right after installing Limitless Sound. It opens every app
through the hub, the way the settings page does, then runs the Limitless Access Standard
test kit against each one: the app must join the suite, announce its actions and answer
every one of them within 3 seconds. It also times how long each app takes to open,
measures the memory and CPU each one uses while sitting idle, checks the apps work as one
suite (all connected at once, a shared DAW command reaches the right app), and takes
screenshots.

  python3 packaging/proof/prove_suite.py --out proof

Writes proof/proof.json and proof/summary.md. Exits 3 if any app fails (level 1, ready in
time, still running), so a crash of this script itself (exit 1) is told apart.
Standard library only.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "standard" / "conformance"))
import las_check  # noqa: E402

# The order a musician is likely to open them in; every app is tested the same way.
TOOLS = {
    "onehand": ("Limitless One-Hand", "Limitless One-Hand.app"),
    "voice": ("Limitless Voice", "Limitless Voice.app"),
    "zoom": ("Limitless Zoom", "Limitless Zoom.app"),
    "color": ("Limitless Color", "Limitless Color.app"),
    "control": ("Limitless Control", "Limitless Control.app"),
    "gaze": ("GazeStage", "GazeStage.app"),
}
HUB_APP = "Limitless Sound.app"
OPEN_LIMIT = 90.0    # seconds to wait for an app to open and join the suite at all
READY_LIMIT = 15.0   # seconds a musician should ever wait for an app to be ready
IDLE_SECONDS = 15    # how long to watch CPU while everything sits idle
SETTLE_SECONDS = 5   # quiet time after the last action before that
IDLE_CPU_LIMIT = 3.0 # % of one core an app may use sitting idle, so laptops last a session
# A refusal that only says the app didn't answer in time is no answer: the test kit counts any
# refusal with a reason, and GazeStage's 8 unanswered actions on the Intel Mac passed that way.
TIMED_OUT = re.compile(r"(didn[’']t|did not|never) answer|still starting|in time|timed out", re.I)


def run(cmd: list[str], timeout: float = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def computer() -> dict:
    info = {"os": platform.system(), "arch": platform.machine(), "python": platform.python_version()}
    if sys.platform == "darwin":
        info["os"] = f"macOS {run(['sw_vers', '-productVersion'])}"
        info["model"] = run(["sysctl", "-n", "hw.model"])
        info["chip"] = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["memoryGB"] = round(int(run(["sysctl", "-n", "hw.memsize"]) or 0) / 2**30)
    elif sys.platform == "win32":
        info["os"] = f"Windows {platform.version()}"
        info["chip"] = platform.processor()
    return info


def screenshot(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        run(["screencapture", "-x", "-t", "png", str(path)])
    elif sys.platform == "win32":
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
              "$i=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
              "[System.Drawing.Graphics]::FromImage($i).CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
              f"$i.Save('{path}')")
        run(["powershell", "-NoProfile", "-Command", ps])
    return path.exists() and path.stat().st_size > 0


def cpu_seconds(text: str) -> float:
    """CPU time as ps prints it on a Mac ("1:02.53", "1:02:03.04" or "2-01:02:03.04") in seconds."""
    days, _, rest = text.rpartition("-")
    total = 0.0
    for part in rest.split(":"):
        total = total * 60 + float(part)
    return total + (int(days) * 86400 if days else 0)


def processes() -> dict[int, tuple[str, float, int]]:
    """pid -> (command, CPU seconds used so far, memory bytes), on a Mac."""
    out = {}
    for line in run(["ps", "-axo", "pid=,time=,rss=,command="]).splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            with contextlib.suppress(ValueError):
                out[int(parts[0])] = (parts[3], cpu_seconds(parts[1]), int(parts[2]) * 1024)
    return out


def windows_processes() -> dict[int, tuple[str, float, int]]:
    """pid -> (program path, CPU seconds used so far, memory bytes), on Windows."""
    ps = ("Get-Process | Where-Object Path | Select-Object Id, Path, CPU, WorkingSet64 "
          "| ConvertTo-Json -Compress")
    try:
        rows = json.loads(run(["powershell", "-NoProfile", "-Command", ps], timeout=60) or "[]")
    except ValueError:
        return {}
    rows = rows if isinstance(rows, list) else [rows]
    return {r["Id"]: (r.get("Path") or "", float(r.get("CPU") or 0), int(r.get("WorkingSet64") or 0)) for r in rows}


def usage(bundles: dict[str, str]) -> dict[str, dict]:
    """CPU and memory of each app (all its helper processes together) while everything sits idle.

    CPU comes from two readings of each app's CPU time IDLE_SECONDS apart. (A Mac's own
    %cpu is a decaying average of the last minute, so it would count the test kit's work.)
    """
    if sys.platform == "win32":
        read = windows_processes
        marks = {k: "\\" + b.removesuffix(".app").lower() + "\\" for k, b in bundles.items()}
    elif sys.platform == "darwin":
        read = processes
        marks = {k: f"/{b}/".lower() for k, b in bundles.items()}
    else:
        return {}
    time.sleep(SETTLE_SECONDS)
    before, t0 = read(), time.time()
    time.sleep(IDLE_SECONDS)
    after, took = read(), time.time() - t0
    out = {}
    for key, mark in marks.items():
        mine = [pid for pid, (path, _, _) in after.items() if mark in path.lower()]
        if mine:
            cpu = sum(after[p][1] - before.get(p, after[p])[1] for p in mine) / took * 100
            out[key] = {"cpuPercent": round(max(cpu, 0.0), 1), "memoryMB": round(sum(after[p][2] for p in mine) / 2**20)}
    return out


def wait_for_hub(limit: float) -> las_check.Hub:
    end = time.time() + limit
    while True:
        try:
            hub = las_check.live_hub()
            hub.state()
            return hub
        except Exception:
            if time.time() > end:
                raise
            time.sleep(1)


def connected(hub: las_check.Hub, tool: str) -> bool:
    return any(t["id"] == tool and t["connected"] for t in hub.state()["tools"])


def kit(hub: las_check.Hub, tool: str) -> tuple[las_check.Report, str]:
    """The Access Standard test kit, pressing every action the app announces."""
    args = argparse.Namespace(tool=tool, try_all=True, try_ids=[], wait=5.0, attest=set(), evidence="")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rep = las_check.check(hub, args)
    return rep, buf.getvalue()


def open_app(hub: las_check.Hub, tool: str, name: str, bundle: str) -> dict:
    """Open an app through the hub, as the settings page's Open button does."""
    started = time.time()
    try:
        answer = hub.invoke("hub.open", {"tool": tool})
    except Exception as e:  # the hub itself failed to answer
        answer = {"ok": False, "message": f"The hub didn't answer: {e}"}
    result = {"openedBy": "hub", "hubAnswer": answer.get("message", "")}
    if not answer.get("ok"):
        # Still test the app itself, but the hub's failure stays on the record.
        result["openedBy"] = "fallback"
        if sys.platform == "darwin":
            run(["open", "-g", f"/Applications/{bundle}"])
    while time.time() - started < OPEN_LIMIT:
        if connected(hub, tool):
            result["joinedSeconds"] = round(time.time() - started, 1)
            return result
        time.sleep(0.5)
    result["joinedSeconds"] = None
    return result


def suite_checks(hub: las_check.Hub, tools: list[str]) -> list[dict]:
    """The apps working as one suite, not just one by one."""
    checks = []
    state = hub.state()
    up = sorted(t["id"] for t in state["tools"] if t["connected"])
    missing = sorted(set(tools) - set(up))
    checks.append({"id": "S1", "ok": not missing, "check": "Every app connected to the suite at the same time",
                   "detail": f"missing: {missing}" if missing else f"{len(up)} connected"})
    # A shared DAW command goes to whichever open app can press the DAW's keys.
    started = time.time()
    try:
        r = hub.invoke("daw.zoomIn")
    except Exception as e:
        r = {"ok": False, "message": str(e)}
    took = round(time.time() - started, 2)
    checks.append({"id": "S2", "ok": bool(r.get("ok")) and took <= las_check.REPLY_LIMIT,
                   "check": "A shared DAW command (zoom in) reaches an app and is answered within 3 seconds",
                   "detail": f"{r.get('message', '')} ({took} s)"})
    try:
        r = hub.invoke("hub.status")
        ok = bool(r.get("ok"))
    except Exception as e:
        r, ok = {"message": str(e)}, False
    checks.append({"id": "S3", "ok": ok, "check": "The hub can say which apps are open",
                   "detail": r.get("message", "")})
    return checks


def summary(proof: dict) -> str:
    c = proof["computer"]
    lines = [f"## Limitless Sound {proof['suiteVersion']} on {c.get('model') or c['arch']} ({c['os']})", ""]
    if proof.get("installSeconds") is not None:
        lines.append(f"Installed in {proof['installSeconds']} s.")
    lines += ["", "| App | Opened by | Joined in | Level | Actions answered | Idle CPU | Memory |",
              "|---|---|---|---|---|---|---|"]
    for a in proof["apps"]:
        level = {None: "❌ none", "connected": "1 Connected", "adaptive": "2 Adaptive"}.get(a["level"], a["level"])
        c4 = next((x for x in a["checks"] if x["id"] == "C4"), None)
        u = a.get("idle") or {}
        lines.append(f"| {a['name']} | {a['openedBy']} | {a['joinedSeconds'] if a['joinedSeconds'] is not None else '—'} s "
                     f"| {level} | {'✅' if c4 and c4['ok'] else '❌'} {a['actionsTried']} "
                     f"| {u.get('cpuPercent', '—')}% | {u.get('memoryMB', '—')} MB |")
    lines += ["", "| Suite check | Result |", "|---|---|"]
    lines += [f"| {s['check']} | {'✅' if s['ok'] else '❌'} {s['detail']} |" for s in proof["suite"]]
    failures = [f"- **{a['name']}** {x['id']}: {x['check']} — {x['detail']}"
                for a in proof["apps"] for x in a["checks"] + a["proof"]
                if not x["ok"] and not x.get("warn") and x.get("level", "proof") in ("connected", "proof")]
    warnings = [f"- **{a['name']}** {x['id']}: {x['check']} — {x['detail']}"
                for a in proof["apps"] for x in a["proof"] if not x["ok"] and x.get("warn")]
    if failures:
        lines += ["", "### What failed", *failures]
    if warnings:
        lines += ["", "### To improve", *warnings]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="proof", help="folder for proof.json, summary.md and screenshots")
    p.add_argument("--suite-version", default="", help="the suite version that was installed")
    p.add_argument("--install-seconds", type=float, default=None)
    p.add_argument("--tools", default=",".join(TOOLS), help="comma-separated tool ids to test")
    args = p.parse_args(argv)
    # Windows writes to a pipe in its old code page, which has no ✅: the first Windows proof
    # stopped there, after every app had passed.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = [t for t in args.tools.split(",") if t in TOOLS]

    hub = wait_for_hub(60)
    screenshot(out / "shots" / "hub.png")
    proof = {"when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "standard": las_check.STANDARD,
             "suiteVersion": args.suite_version, "installSeconds": args.install_seconds,
             "computer": computer(), "apps": [], "suite": []}

    for tool in tools:
        name, bundle = TOOLS[tool]
        print(f"\n=== {name}", flush=True)
        app = {"tool": tool, "name": name, **open_app(hub, tool, name, bundle)}
        print(f"opened by {app['openedBy']} ({app['hubAnswer']}); joined in {app['joinedSeconds']} s", flush=True)
        time.sleep(3)  # let its windows finish drawing
        app["screenshot"] = f"shots/{tool}.png" if screenshot(out / "shots" / f"{tool}.png") else ""
        rep, log = kit(hub, tool)
        print(log, flush=True)
        passed = [lvl for lvl in las_check.LEVELS
                  if all(rep.level_ok(x) for x in las_check.LEVELS[:las_check.LEVELS.index(lvl) + 1])]
        app["level"] = passed[-1] if passed else None
        app["checks"] = rep.checks
        joined = app["joinedSeconds"]
        app["proof"] = [
            {"id": "P1", "ok": joined is not None and joined <= READY_LIMIT,
             "check": f"Ready within {READY_LIMIT:.0f} seconds of opening",
             "detail": f"{joined} s" if joined is not None else f"not ready after {OPEN_LIMIT:.0f} s"},
            {"id": "P2", "ok": connected(hub, tool),
             "check": "Still running after every one of its actions was pressed",
             "detail": "" if connected(hub, tool) else "It quit or crashed. See the crash report in the log."},
        ]
        timed_out = [f"{a}: {m}" for a, m in rep.refused if TIMED_OUT.search(m)]
        app["proof"].append({"id": "P4", "ok": not timed_out,
                             "check": "Every action ran, or was refused for a reason, never timed out",
                             "detail": "; ".join(timed_out)})
        app["actionsTried"] = len([a for a in hub.state()["actions"] if a.get("tool") == tool and a.get("live")])
        state = hub.state()
        app["version"] = next((t["version"] for t in state["tools"] if t["id"] == tool), "")
        proof["apps"].append(app)

    print("\n=== The suite together", flush=True)
    proof["suite"] = suite_checks(hub, tools)
    for s in proof["suite"]:
        print(f"  {'PASS' if s['ok'] else 'FAIL'}  {s['id']}  {s['check']}  {s['detail']}", flush=True)
    idle = usage({t: TOOLS[t][1] for t in tools} | {"hub": HUB_APP})
    for a in proof["apps"]:
        a["idle"] = idle.get(a["tool"], {})
        cpu = a["idle"].get("cpuPercent")
        a["proof"].append({"id": "P3", "ok": cpu is not None and cpu <= IDLE_CPU_LIMIT, "warn": True,
                           "check": f"Uses under {IDLE_CPU_LIMIT:.0f}% CPU sitting idle",
                           "detail": f"{cpu}%" if cpu is not None else "not running"})
    proof["hubIdle"] = idle.get("hub", {})
    screenshot(out / "shots" / "all.png")

    (out / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    text = summary(proof)
    (out / "summary.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    ok = (all(a["level"] for a in proof["apps"]) and all(s["ok"] for s in proof["suite"])
          and all(x["ok"] for a in proof["apps"] for x in a["proof"] if not x.get("warn")))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
