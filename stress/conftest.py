"""Shared helpers for the Limitless Sound stress suite.

The suite lives at the repository root and reaches into each app's folder. An app
that isn't in this checkout yet (its pull request hasn't merged) is skipped, so the
suite can land first and switch each app's tests on as the app arrives.

STRESS_SECONDS sets how long the soak tests run (default 20; the nightly run uses 600).
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("STRESS_REPO_ROOT") or Path(__file__).resolve().parents[1])
SOAK_SECONDS = float(os.environ.get("STRESS_SECONDS", "20"))

APP_PATHS = {
    "hub": [ROOT / "shared" / "hub", ROOT / "shared" / "clients" / "python"],
    "onehand": [ROOT / "apps" / "one-hand"],
    "voice": [ROOT / "apps" / "voice"],
    "control": [ROOT / "apps" / "control"],
    "zoom": [ROOT / "apps" / "zoom"],
}
MARKERS = {
    "hub": "limitless_hub", "onehand": "onehand", "voice": "limitless_voice",
    "control": "limitless_control", "zoom": "limitless_zoom",
}


def need(app: str) -> None:
    """Put an app's code on the import path, or skip the module when it isn't here."""
    base = APP_PATHS[app][0]
    if not (base / MARKERS[app]).is_dir():
        pytest.skip(f"{base.relative_to(ROOT)} is not in this checkout yet", allow_module_level=True)
    for p in APP_PATHS[app]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def rss_mb() -> float:
    import psutil
    return psutil.Process().memory_info().rss / 1e6


def wait_for(cond, timeout=5.0, step=0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return bool(cond())


def percentile(values, p):
    s = sorted(values)
    if not s:
        return 0.0
    return s[min(len(s) - 1, int(len(s) * p))]


class Soak:
    """Samples memory and threads once a second while a soak runs, then judges growth.

    Growth is measured from the end of a warm-up (allocator pools, caches and
    first-use imports settle in the first seconds), so a steady state passes and
    a leak that keeps climbing fails.
    """

    def __init__(self, seconds: float = SOAK_SECONDS):
        self.seconds = seconds
        self.samples: list[tuple[float, float, int]] = []

    def run(self, step) -> int:
        start = time.monotonic()
        last = 0.0
        n = 0
        while (now := time.monotonic()) - start < self.seconds:
            step(n)
            n += 1
            if now - last >= 1.0:
                gc.collect()
                self.samples.append((now - start, rss_mb(), threading.active_count()))
                last = now
        gc.collect()
        self.samples.append((time.monotonic() - start, rss_mb(), threading.active_count()))
        return n

    def growth(self) -> tuple[float, int]:
        warm = [s for s in self.samples if s[0] >= min(5.0, self.seconds / 4)] or self.samples
        return warm[-1][1] - warm[0][1], warm[-1][2] - warm[0][2]

    def report(self) -> str:
        mem, threads = self.growth()
        return (f"{len(self.samples)} samples, memory {self.samples[0][1]:.1f} → {self.samples[-1][1]:.1f} MB "
                f"(+{mem:.1f} after warm-up), threads {self.samples[0][2]} → {self.samples[-1][2]}")
