"""Reads the Xbox Adaptive Controller (or any gamepad SDL knows) and reports named inputs.

SDL's game controller layer gives every pad the same Xbox-style names on Mac,
Windows and Linux, so profiles work everywhere. Each 3.5 mm jack on the
Adaptive Controller reports as one of these buttons.
"""

from __future__ import annotations

import os
from typing import Callable

# Keep receiving the controller while Logic, Pro Tools or another app is in front.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
# On Mac, stay a background app: no Dock icon and never take focus from the DAW.
os.environ.setdefault("SDL_MAC_BACKGROUND_APP", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
from pygame._sdl2 import controller as sdl_controller  # noqa: E402

BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: "a",
    pygame.CONTROLLER_BUTTON_B: "b",
    pygame.CONTROLLER_BUTTON_X: "x",
    pygame.CONTROLLER_BUTTON_Y: "y",
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "lb",
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb",
    pygame.CONTROLLER_BUTTON_BACK: "view",
    pygame.CONTROLLER_BUTTON_START: "menu",
    pygame.CONTROLLER_BUTTON_GUIDE: "xbox",
    pygame.CONTROLLER_BUTTON_LEFTSTICK: "ls",
    pygame.CONTROLLER_BUTTON_RIGHTSTICK: "rs",
    pygame.CONTROLLER_BUTTON_DPAD_UP: "dpad_up",
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: "dpad_down",
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: "dpad_left",
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "dpad_right",
}

# Axis -> (name when negative, name when positive). SDL's Y axes point down.
AXES = {
    pygame.CONTROLLER_AXIS_LEFTX: ("lstick_left", "lstick_right"),
    pygame.CONTROLLER_AXIS_LEFTY: ("lstick_up", "lstick_down"),
    pygame.CONTROLLER_AXIS_RIGHTX: ("rstick_left", "rstick_right"),
    pygame.CONTROLLER_AXIS_RIGHTY: ("rstick_up", "rstick_down"),
    pygame.CONTROLLER_AXIS_TRIGGERLEFT: (None, "lt"),
    pygame.CONTROLLER_AXIS_TRIGGERRIGHT: (None, "rt"),
}

# A trigger or stick counts as released only once it falls this far below the
# push point, so a shaky hand resting near the threshold doesn't fire again and again.
HYSTERESIS = 0.2

ALL_INPUTS = [
    "a", "b", "x", "y", "lb", "rb", "lt", "rt", "view", "menu", "xbox", "ls", "rs",
    "dpad_up", "dpad_down", "dpad_left", "dpad_right",
    "lstick_up", "lstick_down", "lstick_left", "lstick_right",
    "rstick_up", "rstick_down", "rstick_left", "rstick_right",
]


class ControllerReader:
    def __init__(self, on_press: Callable[[str], None], on_release: Callable[[str], None],
                 log: Callable[[str], None]):
        self.on_press = on_press
        self.on_release = on_release
        self.log = log
        self.threshold = 0.6
        self._pads: dict[int, sdl_controller.Controller] = {}
        self._down: dict[int, set[str]] = {}

    def start(self) -> None:
        # The event queue needs SDL's video system, but no window is ever opened.
        # Without a window system (a Mac build server, a Linux service) fall back
        # to SDL's dummy video driver; controller input still arrives.
        try:
            pygame.display.init()
        except pygame.error as exc:
            self.log(f"No window system ({exc}); using background video driver")
            pygame.display.quit()
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            pygame.display.init()
        pygame.joystick.init()
        sdl_controller.init()
        for i in range(sdl_controller.get_count()):
            self._open(i)

    @property
    def video_driver(self) -> str:
        try:
            return pygame.display.get_driver()
        except pygame.error:
            return ""

    @property
    def held(self) -> list[str]:
        return sorted(set().union(*self._down.values())) if self._down else []

    @property
    def connected(self) -> list[str]:
        return [pad.name for pad in self._pads.values()]

    def _open(self, index: int) -> None:
        if not sdl_controller.is_controller(index):
            return
        try:
            pad = sdl_controller.Controller(index)
        except pygame.error as exc:
            self.log(f"Could not open controller {index}: {exc}")
            return
        jid = pad.as_joystick().get_instance_id()
        if jid not in self._pads:
            self._pads[jid] = pad
            self._down[jid] = set()
            self.log(f"Connected: {pad.name}")

    def _set(self, jid: int, name: str, down: bool) -> None:
        held = self._down.setdefault(jid, set())
        if down and name not in held:
            held.add(name)
            self.on_press(name)
        elif not down and name in held:
            held.discard(name)
            self.on_release(name)

    def poll(self) -> None:
        """Handle pending controller events. Call often from the main thread."""
        for ev in pygame.event.get():
            if ev.type == pygame.CONTROLLERDEVICEADDED:
                self._open(ev.device_index)
            elif ev.type == pygame.CONTROLLERDEVICEREMOVED:
                pad = self._pads.pop(ev.instance_id, None)
                for name in list(self._down.pop(ev.instance_id, set())):
                    self.on_release(name)
                if pad:
                    self.log(f"Disconnected: {pad.name}")
            elif ev.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
                name = BUTTONS.get(ev.button)
                if name:
                    self._set(ev.instance_id, name, ev.type == pygame.CONTROLLERBUTTONDOWN)
            elif ev.type == pygame.CONTROLLERAXISMOTION:
                neg, pos = AXES.get(ev.axis, (None, None))
                value = ev.value / 32767.0
                held = self._down.get(ev.instance_id, set())
                for name, amount in ((neg, -value), (pos, value)):
                    if not name:
                        continue
                    if name in held:
                        down = amount >= max(self.threshold - HYSTERESIS, 0.1)
                    else:
                        down = amount >= self.threshold
                    self._set(ev.instance_id, name, down)

    def stop(self) -> None:
        sdl_controller.quit()
        pygame.quit()
