"""Text size, high contrast and reduced motion, for every window.

Each comes from Limitless Voice's own settings and, with the Limitless Sound
hub running, from the suite's shared settings. The more accessible of the two
wins: the larger text, and high contrast or reduced motion if either asks for it.
Without the hub, only Voice's own settings count.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

TEXT_SIZE = "textSize"   # widget property: its text size, as a multiple of the normal size


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
