# PyInstaller build: pyinstaller packaging/limitless_keys.spec
# Produces dist/Limitless Keys.app on macOS. If plugins/ holds a built Limitless Undo
# (Limitless Undo.component, .vst3...), it goes inside the app for Setup to install.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from limitless_keys import __version__  # noqa: E402

datas = [(str(ROOT / "limitless_keys" / "resources"), "limitless_keys/resources")]
plugins = ROOT / "plugins"
if plugins.is_dir():
    for p in plugins.iterdir():
        if p.suffix in (".component", ".vst3", ".aaxplugin"):
            datas.append((str(p), f"plugins/{p.name}"))

if sys.platform == "darwin":
    hidden = ["pynput.keyboard._darwin", "pynput.mouse._darwin", "AppKit", "Quartz",
              "ApplicationServices", "CoreFoundation", "Foundation", "objc"]
else:
    hidden = ["pynput.keyboard._xorg", "pynput.mouse._xorg"]

a = Analysis([str(ROOT / "limitless_keys" / "__main__.py")], pathex=[str(ROOT)],
             datas=datas,
             hiddenimports=hidden + ["PySide6.QtTextToSpeech", "PySide6.QtNetwork"],
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick"])
pyz = PYZ(a.pure)
icon = ROOT / "packaging" / "icon.icns"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Limitless Keys", console=False,
          icon=str(icon) if sys.platform == "darwin" else None)
coll = COLLECT(exe, a.binaries, a.datas, name="Limitless Keys")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="Limitless Keys.app", bundle_identifier="org.limitlesssound.keys",
                 icon=str(icon),
                 info_plist={
                     "CFBundleDisplayName": "Limitless Keys",
                     "CFBundleShortVersionString": __version__,
                     "CFBundleVersion": __version__,
                     "LSMinimumSystemVersion": "12.0",
                     "LSUIElement": True,          # menu bar app, no Dock icon
                     "NSAppSleepDisabled": True,   # no App Nap: it answers shortcuts from the background
                     "NSHighResolutionCapable": True,
                 })
