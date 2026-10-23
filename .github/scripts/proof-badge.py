#!/usr/bin/env python3
"""The proof's badge: latest.json in, badge.svg out. The README shows it, so anyone landing on the
repo sees whether the public download passed on fresh computers, and which version.

A computer passes when its run finished, every suite check passed (S1...), and every app passed
the way the website counts it: it reached a level, and each of its proof checks passed or only
warned.

  proof-badge.py latest.json badge.svg
"""
import json
import sys
from html import escape


def passed(run):
    if run.get("error"):
        return False
    apps_ok = all(a.get("level") and all(c.get("ok") or c.get("warn") for c in a.get("proof", []))
                  for a in run.get("apps", []))
    return apps_ok and all(c.get("ok") for c in run.get("suite", []))


def words(data):
    runs = data.get("runs", [])
    if not runs:
        return "no results yet", "#555"
    good = sum(passed(r) for r in runs)
    version = next((r.get("suiteVersion") for r in runs if r.get("suiteVersion")), "")
    if runs and good == len(runs):
        return f"{version} passes on {len(runs)} of {len(runs)} computers".strip(), "#2e7d32"
    return f"{version} passes on {good} of {len(runs)} computers".strip(), "#c62828"


def svg(label, value, colour):
    # Verdana 11 px is about 6.5 px a character; the badge only needs to be roughly right.
    lw, vw = 10 + round(6.5 * len(label)), 10 + round(6.5 * len(value))
    w = lw + vw
    text = escape(f"{label}: {value}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{text}">
<title>{text}</title>
<rect width="{lw}" height="20" fill="#444"/><rect x="{lw}" width="{vw}" height="20" fill="{colour}"/>
<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2}" y="14" text-anchor="middle">{escape(label)}</text>
<text x="{lw + vw / 2}" y="14" text-anchor="middle">{escape(value)}</text>
</g>
</svg>
"""


def main(argv):
    data = json.loads(open(argv[0], encoding="utf-8").read())
    value, colour = words(data)
    open(argv[1], "w", encoding="utf-8").write(svg("proof on fresh computers", value, colour))
    print(f"badge: {value}")


if __name__ == "__main__":
    main(sys.argv[1:])
