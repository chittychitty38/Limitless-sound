"""Draws the app icon and writes icon.png, icon.icns (Mac) and icon.ico (Windows).
Run: python packaging/make_icon.py   (needs PySide6 and Pillow)"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "limitless_zoom" / "resources"


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

    # waveform inside the lens
    centre = QPointF(450 * s, 450 * s)
    radius = 235 * s
    clip = QPainterPath()
    clip.addEllipse(centre, radius, radius)
    p.save()
    p.setClipPath(clip)
    p.setBrush(QColor("#4fc3f7"))
    heights = [60, 120, 210, 300, 380, 300, 220, 330, 250, 150, 90, 50]
    bar_w, gap = 26 * s, 12 * s
    x = centre.x() - (len(heights) * (bar_w + gap) - gap) / 2
    for h in heights:
        h *= s
        p.drawRoundedRect(QRectF(x, centre.y() - h / 2, bar_w, h), bar_w / 2, bar_w / 2)
        x += bar_w + gap
    p.restore()

    # lens ring and handle
    pen = QPen(QColor("#ffcc00"), 62 * s, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(centre, radius, radius)
    pen.setWidthF(92 * s)
    p.setPen(pen)
    p.drawLine(QPointF(632 * s, 632 * s), QPointF(790 * s, 790 * s))
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
    im.save(ROOT / "packaging" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                    (64, 64), (128, 128), (256, 256)])
    im.resize((256, 256), Image.LANCZOS).save(png)  # small copy for the tray and windows
    print("wrote", png)


if __name__ == "__main__":
    main()
