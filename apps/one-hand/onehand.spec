# PyInstaller recipe: builds "Limitless One-Hand.app" on macOS and LimitlessOneHand.exe on Windows.
import re
import sys

VERSION = re.search(r'__version__ = "([^"]+)"', open("onehand/__init__.py").read()).group(1)

a = Analysis(
    ["main.py"],
    datas=[("onehand/layouts.json", "onehand")],
    hiddenimports=["onehand.platform_mac", "onehand.platform_win"] if sys.platform != "linux" else [],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Limitless One-Hand", console=False,
              icon="assets/icon.png")
    coll = COLLECT(exe, a.binaries, a.datas, name="Limitless One-Hand")
    app = BUNDLE(
        coll,
        name="Limitless One-Hand.app",
        icon="assets/icon.png",
        bundle_identifier="org.limitlesssound.onehand",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Limitless One-Hand",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSApplicationCategoryType": "public.app-category.music",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Limitless Sound. Music software that leaves no one out.",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="LimitlessOneHand", console=False,
              icon="assets/icon.png")
