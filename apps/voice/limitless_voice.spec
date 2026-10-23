# PyInstaller recipe for Limitless Voice. Build with:
#   pyinstaller limitless_voice.spec
# The speech model must be unpacked in ./models first (CI does this).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

sys.path.insert(0, str(Path(SPECPATH)))
from limitless_voice import __version__  # noqa: E402

MODEL = "vosk-model-small-en-us-0.15"
APP = "Limitless Voice"
mac = sys.platform == "darwin"
win = sys.platform.startswith("win")

datas = [
    ("limitless_voice/packs", "limitless_voice/packs"),
    ("limitless_voice/languages", "limitless_voice/languages"),   # every language's words; models are downloaded
    ("limitless_voice/assets", "limitless_voice/assets"),
    (f"models/{MODEL}", f"models/{MODEL}"),
]
datas += collect_data_files("vosk")
binaries = collect_dynamic_libs("vosk")

hidden = ["yaml", "platformdirs"]
if mac:
    hidden += ["pynput.keyboard._darwin", "pynput.mouse._darwin", "AppKit", "ApplicationServices", "AVFoundation", "ServiceManagement"]
elif win:
    hidden += ["pynput.keyboard._win32", "pynput.mouse._win32",
               "pyttsx3.drivers", "pyttsx3.drivers.sapi5", "comtypes", "comtypes.client"]
else:
    hidden += ["pynput.keyboard._xorg", "pynput.mouse._xorg", "pyttsx3.drivers", "pyttsx3.drivers.espeak"]

# Qt pieces we don't use; leaving them out saves well over 100 MB
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "tkinter", "numpy",
]

a = Analysis(
    ["run_app.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LimitlessVoice" if win else APP,
    console=False,
    icon="limitless_voice/assets/icon.ico" if win else "limitless_voice/assets/icon.png",
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP)

if mac:
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon="limitless_voice/assets/icon.png",
        bundle_identifier="org.limitlesssound.voice",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": __version__,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Limitless Voice listens for your spoken commands. Audio never leaves this Mac.",
            "NSAppleEventsUsageDescription":
                "Limitless Voice can click menu items in apps you control by voice.",
        },
    )
