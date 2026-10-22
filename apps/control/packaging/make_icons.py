"""Draws the Limitless Control app icon and writes .icns (Mac), .ico (Windows) and .png.

Run from apps/control:  python packaging/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
OUT = Path(__file__).parent / "icons"


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Background: macOS-sized rounded square with a deep blue to violet gradient.
    grad = Image.new("RGBA", (S, S))
    top, bottom = (24, 92, 222), (108, 52, 196)
    px = grad.load()
    for y in range(S):
        t = y / (S - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        for x in range(S):
            px[x, y] = c
    mask = Image.new("L", (S, S), 0)
    m = 100  # Apple's icon grid leaves a margin around the rounded square
    ImageDraw.Draw(mask).rounded_rectangle((m, m, S - m, S - m), radius=185, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    # Adaptive Controller: a wide body with two big round pads and a d-pad.
    d.rounded_rectangle((190, 410, 834, 750), radius=120, fill=white)
    blue = (40, 80, 210, 255)
    violet = (110, 60, 200, 255)
    d.ellipse((470, 470, 610, 610), fill=blue)        # A
    d.ellipse((640, 470, 780, 610), fill=violet)      # B
    cx, cy, a, w = 320, 580, 62, 40                    # d-pad
    d.rounded_rectangle((cx - w // 2, cy - a, cx + w // 2, cy + a), radius=10, fill=blue)
    d.rounded_rectangle((cx - a, cy - w // 2, cx + a, cy + w // 2), radius=10, fill=blue)
    # Sound waves rising from the controller.
    for i, r in enumerate((90, 150, 210)):
        box = (512 - r, 390 - r, 512 + r, 390 + r)
        d.arc(box, start=215, end=325, fill=(255, 255, 255, 235 - i * 55), width=26)
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    img.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()


def dmg_background() -> None:
    """The window shown when the .dmg opens: app on the left, Applications on the right."""
    from PIL import ImageFont
    w, h, scale = 640, 400, 2
    img = Image.new("RGB", (w * scale, h * scale), (246, 247, 251))
    d = ImageDraw.Draw(img)

    def font(size, bold=False):
        names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
        for name in names:
            try:
                return ImageFont.truetype(name, size * scale)
            except OSError:
                continue
        return ImageFont.load_default()

    def centered(y, text, f, fill):
        tw = d.textlength(text, font=f)
        d.text(((w * scale - tw) / 2, y * scale), text, font=f, fill=fill)

    centered(36, "Limitless Control", font(26, bold=True), (24, 30, 60))
    centered(76, "Drag the app onto Applications to install it.", font(15), (70, 76, 100))
    # Arrow between the two icons (icons sit at x=170 and x=470, y=210).
    y = 210 * scale
    d.line((255 * scale, y, 375 * scale, y), fill=(60, 90, 210), width=8 * scale // 2)
    d.polygon([(390 * scale, y), (366 * scale, y - 16 * scale), (366 * scale, y + 16 * scale)], fill=(60, 90, 210))
    centered(330, "Then open it from Applications. It lives in your menu bar.", font(13), (90, 96, 120))
    img.save(OUT / "dmg-background@2x.png")
    img.resize((w, h), Image.LANCZOS).save(OUT / "dmg-background.png")


if __name__ == "__main__":
    dmg_background()
