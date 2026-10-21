# PyInstaller build for Mac (.app), Windows and Linux.
# Run from the project root:  pyinstaller packaging/limitless_control.spec
import re
import sys
from pathlib import Path

root = Path(SPECPATH).parent
version = re.search(r'__version__ = "([^"]+)"', (root / "limitless_control" / "__init__.py").read_text()).group(1)
icons = root / "packaging" / "icons"

hidden = ["pynput.keyboard._darwin", "pynput.keyboard._win32", "pynput.keyboard._xorg",
          "pynput.mouse._darwin", "pynput.mouse._win32", "pynput.mouse._xorg"]
if sys.platform.startswith("win"):
    hidden += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5"]
if sys.platform == "darwin":
    hidden += ["AppKit", "Foundation", "objc", "HIServices"]

a = Analysis(
    [str(root / "packaging" / "launch.py")],
    pathex=[str(root)],
    datas=[(str(root / "limitless_control" / "web"), "limitless_control/web")],
    hiddenimports=hidden,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Limitless Control",
    console=False,
    argv_emulation=False,
    icon=str(icons / ("icon.ico" if sys.platform.startswith("win") else "icon.icns")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Limitless Control")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Limitless Control.app",
        bundle_identifier="org.limitlesssound.control",
        icon=str(icons / "icon.icns"),
        version=version,
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleDisplayName": "Limitless Control",
            # Runs in the background: no Dock icon. Opening the app again shows settings.
            "LSUIElement": True,
            "NSHumanReadableCopyright": "Limitless Sound",
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.music",
        },
    )
