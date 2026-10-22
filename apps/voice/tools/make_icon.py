"""Draw the app icon (a microphone in a sound wave ring) as PNG and ICO.

Run once; the results are committed in limitless_voice/assets/.
  QT_QPA_PLATFORM=offscreen python tools/make_icon.py
"""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

OUT = Path(__file__).resolve().parent.parent / "limitless_voice" / "assets"


def draw(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 1024
    # rounded square background
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#14213d"))
    p.drawRoundedRect(QRectF(40 * s, 40 * s, 944 * s, 944 * s), 200 * s, 200 * s)
    # sound wave rings
    for i, alpha in enumerate((255, 170, 90)):
        pen = QPen(QColor(255, 196, 0, alpha), 44 * s)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        r = (250 + i * 90) * s
        rect = QRectF(512 * s - r, 500 * s - r, 2 * r, 2 * r)
        p.drawArc(rect, -35 * 16, 70 * 16)
        p.drawArc(rect, 145 * 16, 70 * 16)
    # microphone body
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(422 * s, 230 * s, 180 * s, 330 * s), 90 * s, 90 * s)
    pen = QPen(QColor("#ffffff"), 40 * s)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(352 * s, 330 * s, 320 * s, 320 * s), 180 * 16, 180 * 16)
    p.drawLine(int(512 * s), int(650 * s), int(512 * s), int(770 * s))
    p.drawLine(int(420 * s), int(780 * s), int(604 * s), int(780 * s))
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    draw(1024).save(str(OUT / "icon.png"))
    draw(256).save(str(OUT / "icon.ico"))
    print("wrote", OUT / "icon.png", OUT / "icon.ico")
