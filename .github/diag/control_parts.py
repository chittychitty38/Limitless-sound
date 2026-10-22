# What each part of Limitless Control's loop costs while nothing is plugged in, on its own.
import os
import sys
import time

sys.path.insert(0, "apps/control")
SECONDS = 20


def measure(label, body, interval):
    t0, w0 = time.process_time(), time.monotonic()
    n = 0
    while time.monotonic() < w0 + SECONDS:
        body()
        n += 1
        time.sleep(interval)
    cpu = (time.process_time() - t0) / (time.monotonic() - w0) * 100
    print(f"{label:<58} {cpu:5.2f}%  ({n / SECONDS:.0f} a second)", flush=True)


measure("sleeping 50 ms, nothing else", lambda: None, 0.05)
from limitless_control import frontmost  # noqa: E402
measure("which app is in front, 20 a second (Control: 2.5 a second)", frontmost.frontmost_app, 0.05)
from limitless_control.controller import ControllerReader  # noqa: E402
import pygame  # noqa: E402
r = ControllerReader(lambda n: None, lambda n: None, print)
r.start()
print("video driver:", r.video_driver, "| SDL", pygame.get_sdl_version(), flush=True)
measure("controller events (pygame.event.get), 20 a second", r.poll, 0.05)
measure("controller events, 10 a second", r.poll, 0.1)
measure("controller events, 4 a second", r.poll, 0.25)
t0, w0 = time.process_time(), time.monotonic()
while time.monotonic() < w0 + SECONDS:
    pygame.event.wait(250)
print(f"{'waiting for controller events (pygame.event.wait 250 ms)':<58} {(time.process_time() - t0) / (time.monotonic() - w0) * 100:5.2f}%", flush=True)
