# PyInstaller recipe: builds "Limitless One-Hand.app" on macOS and LimitlessOneHand.exe on Windows.
import sys

a = Analysis(
    ["main.py"],
    datas=[("onehand/layouts.json", "onehand")],
    hiddenimports=["onehand.platform_mac", "onehand.platform_win"] if sys.platform != "linux" else [],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Limitless One-Hand", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Limitless One-Hand")
    app = BUNDLE(
        coll,
        name="Limitless One-Hand.app",
        bundle_identifier="org.limitlesssound.onehand",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="LimitlessOneHand", console=False)
