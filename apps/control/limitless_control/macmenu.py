"""Menu bar icon on Mac: shows the controller is running and gives quick controls.

Needs SDL's Cocoa video driver, which runs the Mac event loop for us whenever the
controller is polled. Without it (a build server) the menu bar is skipped.
"""

from __future__ import annotations

from typing import Callable


class MenuBar:
    def __init__(self, open_settings: Callable[[], None], toggle: Callable[[], None],
                 next_layer: Callable[[], None], quit_app: Callable[[], None]):
        from AppKit import NSMenu, NSMenuItem, NSObject, NSStatusBar, NSVariableStatusItemLength

        class LimitlessMenuTarget(NSObject):
            def openSettings_(self, sender):
                open_settings()

            def toggle_(self, sender):
                toggle()

            def nextLayer_(self, sender):
                next_layer()

            def quit_(self, sender):
                quit_app()

        self.target = LimitlessMenuTarget.alloc().init()
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.button = self.item.button()
        self.button.setToolTip_("Limitless Control")

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        def add(title, action=None, key=""):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            if action:
                item.setTarget_(self.target)
            else:
                item.setEnabled_(False)
            menu.addItem_(item)
            return item

        self.status_line = add("Starting…")
        self.profile_line = add("")
        self.pad_line = add("")
        menu.addItem_(NSMenuItem.separatorItem())
        self.toggle_item = add("Turn controller off", "toggle:", "")
        self.layer_item = add("Use layer 2 for the next switch", "nextLayer:", "")
        menu.addItem_(NSMenuItem.separatorItem())
        add("Open Settings…", "openSettings:", ",")
        add("Quit Limitless Control", "quit:", "q")
        self.item.setMenu_(menu)
        self._last = None
        self.update(True, 1, None, [])

    def _icon(self, name: str, description: str):
        from AppKit import NSImage
        try:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, description)
        except AttributeError:  # macOS 10.15 and earlier
            image = None
        if image is not None:
            image.setTemplate_(True)
        return image

    def update(self, enabled: bool, layer: int, profile: str | None, controllers: list[str]) -> None:
        state = (enabled, layer, profile, tuple(controllers))
        if state == self._last:
            return
        self._last = state
        description = "Limitless Control on" if enabled else "Limitless Control off"
        image = self._icon("gamecontroller.fill" if enabled else "gamecontroller", description)
        if image is not None:
            self.button.setImage_(image)
            self.button.setTitle_(" 2" if layer > 1 else "")
        else:
            self.button.setTitle_(("LC" if enabled else "LC off") + (" 2" if layer > 1 else ""))
        self.button.setAppearsDisabled_(not enabled)
        self.button.setAccessibilityLabel_(description + (f", layer {layer}" if layer > 1 else ""))

        self.status_line.setTitle_("Controller is on" if enabled else "Controller is off")
        self.profile_line.setTitle_(f"Profile: {profile or 'none'}" + (f" · layer {layer}" if layer > 1 else ""))
        self.pad_line.setTitle_(", ".join(controllers) if controllers else "No controller connected")
        self.toggle_item.setTitle_("Turn controller off" if enabled else "Turn controller on")
        self.layer_item.setEnabled_(enabled)
