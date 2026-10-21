# PyInstaller build: pyinstaller packaging/limitless_zoom.spec
# Produces dist/Limitless Zoom.app on macOS, dist/Limitless Zoom/ on Windows and Linux.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from limitless_zoom import __version__  # noqa: E402

datas = collect_data_files("vosk") + collect_data_files("_sounddevice_data")
datas.append((str(ROOT / "limitless_zoom" / "resources"), "limitless_zoom/resources"))
if (ROOT / "models").is_dir():
    datas.append((str(ROOT / "models"), "models"))
binaries = collect_dynamic_libs("vosk")

if sys.platform == "darwin":
    hidden = ["pynput.keyboard._darwin", "pynput.mouse._darwin", "AppKit", "Quartz",
              "ApplicationServices", "AVFoundation", "Foundation", "objc"]
elif sys.platform.startswith("win"):
    hidden = ["pynput.keyboard._win32", "pynput.mouse._win32"]
else:
    hidden = ["pynput.keyboard._xorg", "pynput.mouse._xorg"]

a = Analysis([str(ROOT / "limitless_zoom" / "__main__.py")], pathex=[str(ROOT)],
             binaries=binaries, datas=datas,
             hiddenimports=hidden + ["PySide6.QtTextToSpeech", "PySide6.QtNetwork"],
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick"])
pyz = PYZ(a.pure)
icon = ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Limitless Zoom",
          console=False, icon=str(icon))
coll = COLLECT(exe, a.binaries, a.datas, name="Limitless Zoom")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="Limitless Zoom.app", bundle_identifier="org.limitlesssound.zoom",
                 icon=str(icon),
                 info_plist={
                     "CFBundleDisplayName": "Limitless Zoom",
                     "CFBundleShortVersionString": __version__,
                     "CFBundleVersion": __version__,
                     "LSMinimumSystemVersion": "12.0",
                     "LSUIElement": True,  # menu bar app, no Dock icon
                     "NSAppSleepDisabled": True,  # no App Nap: it works from the background
                     "NSMicrophoneUsageDescription":
                         "Limitless Zoom listens for spoken zoom commands like \"zoom in\". "
                         "Audio never leaves your Mac.",
                     "NSHighResolutionCapable": True,
                 })
