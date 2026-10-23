"""Text size, high contrast and reduced motion, for every window.

Each comes from Limitless Voice's own settings and, with the Limitless Sound
hub running, from the suite's shared settings. The more accessible of the two
wins: the larger text, and high contrast or reduced motion if either asks for it.
Without the hub, only Voice's own settings count.

LiveText is for words that change on screen, so a screen reader follows them too.
"""

from PySide6.QtGui import QAccessible, QAccessibleValueChangeEvent, QFont
from PySide6.QtWidgets import QApplication, QLabel

from . import words

TEXT_SIZE = "textSize"   # widget property: its text size, as a multiple of the normal size


def label(text):
    """A label whose words follow Voice's language."""
    lbl = QLabel()
    words.show(lbl.setText, text)
    return lbl


def add_item(combo, text, data=None):
    """An item in a pop-up menu, its words following Voice's language."""
    combo.addItem(text, data)
    words.keep(combo.setItemText, text, combo.count() - 1)


class LiveText(QLabel):
    """Words that change on screen: what was heard, what happened, a permission still needed.
    A screen reader reads the words themselves (on a Mac VoiceOver reads a label's name as its
    words, so these never get a fixed name), `about` says what they are, and each change is
    posted so a screen reader on the label reads the new words. Its words, and what they are,
    follow Voice's language."""

    def __init__(self, about, text=""):
        super().__init__(text)
        words.keep(self.setText, text)
        words.show(self.setAccessibleDescription, about)

    def setText(self, text):
        words.keep(self.setText, text)   # said again in the next language Voice is set to
        super().setText(text)
        # Qt posts the name change itself; VoiceOver follows a label's words as its value.
        iface = QAccessible.queryAccessibleInterface(self)
        QAccessible.updateAccessibility(
            QAccessibleValueChangeEvent(self, iface.text(QAccessible.Name) if iface else text))


def in_use(settings, prefs):
    """What to show now. prefs are the suite's shared settings ({} without the hub).
    The keys are the shared settings Voice honors, as reported back in prefs.applied."""
    return {
        "textScale": max(settings.text_scale, float(prefs.get("textScale") or 0)),
        "highContrast": bool(settings.high_contrast or prefs.get("highContrast")),
        "reduceMotion": bool(prefs.get("reduceMotion")),   # Voice has no setting of its own for this
    }


def sized(widget, factor, bold=False):
    """Text `factor` times the normal size, kept that way whenever the text size changes."""
    widget.setProperty(TEXT_SIZE, factor)
    font = QFont()
    font.setPointSizeF(QApplication.font().pointSizeF() * factor)
    font.setBold(bold)
    widget.setFont(font)
    return widget


def grow(window, factor):
    """Make a window `factor` times bigger so larger text isn't squeezed, never past the screen."""
    if factor <= 1:
        return
    screen = window.screen().availableGeometry().size()
    window.resize((window.size() * factor).boundedTo(screen).expandedTo(window.size()))


def resize_text(point_size):
    """Set the normal text size for every open window, big titles and all."""
    app = QApplication.instance()
    font = QFont(app.font())
    font.setPointSizeF(point_size)
    app.setFont(font)
    if app.styleSheet():
        # under a style sheet, open windows only pick up the new size when it's applied again
        app.setStyleSheet(app.styleSheet())
    for w in app.allWidgets():
        factor = w.property(TEXT_SIZE)
        if factor:
            f = QFont(w.font())
            f.setPointSizeF(point_size * factor)
            w.setFont(f)
