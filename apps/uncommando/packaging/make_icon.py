"""Draws the app icon and writes icon.png and icon.icns.
Run: python packaging/make_icon.py   (needs PySide6 and Pillow)"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "uncommando" / "resources"


def draw(size=1024):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 1024

    # macOS-style rounded square
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0, QColor("#2b2b33"))
    bg.setColorAt(1, QColor("#0e0e12"))
    p.setPen(Qt.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(100 * s, 100 * s, 824 * s, 824 * s), 185 * s, 185 * s)

    # A plugin knob, with a yellow undo arrow sweeping back around it.
    centre, r = QPointF(512 * s, 430 * s), 150 * s
    p.setBrush(QColor("#3a3a44"))
    p.setPen(QPen(QColor("#4fc3f7"), 22 * s))
    p.drawEllipse(centre, r, r)
    p.setPen(QPen(QColor("#ffffff"), 26 * s, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(centre, QPointF(centre.x() + 80 * s, centre.y() - 90 * s))
    arc = QRectF(centre.x() - 230 * s, centre.y() - 230 * s, 460 * s, 460 * s)
    p.setPen(QPen(QColor("#ffcc00"), 44 * s, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(arc, 20 * 16, 200 * 16)
    p.setBrush(QColor("#ffcc00"))
    p.setPen(Qt.NoPen)
    tip = QPointF(centre.x() - 216 * s, centre.y() + 79 * s)
    p.drawPolygon([QPointF(tip.x() - 70 * s, tip.y() - 30 * s), QPointF(tip.x() + 60 * s, tip.y() - 40 * s),
                   QPointF(tip.x() - 10 * s, tip.y() + 80 * s)])

    # The key: ⌥⌘Z
    p.setBrush(QColor("#f2f2f2"))
    p.drawRoundedRect(QRectF(262 * s, 690 * s, 500 * s, 170 * s), 44 * s, 44 * s)
    f = QFont()
    f.setPixelSize(int(118 * s))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#111111"))
    p.drawText(QRectF(262 * s, 690 * s, 500 * s, 170 * s), Qt.AlignCenter, "⌥⌘Z")
    p.end()
    return img


def main():
    QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "icon.png"
    draw().save(str(png))
    from PIL import Image

    im = Image.open(png)
    im.save(ROOT / "packaging" / "icon.icns")
    im.resize((256, 256), Image.LANCZOS).save(png)  # small copy for windows
    print("wrote", png)


if __name__ == "__main__":
    main()
