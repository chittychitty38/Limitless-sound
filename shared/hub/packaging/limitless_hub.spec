# PyInstaller: builds "Limitless Sound" (the hub) for this OS.
#   pyinstaller --noconfirm packaging/limitless_hub.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from limitless_hub import __version__  # noqa: E402

a = Analysis([str(ROOT / "packaging" / "launch.py")], pathex=[str(ROOT)],
             datas=[(str(ROOT / "limitless_hub" / "web"), "limitless_hub/web")],
             excludes=["tkinter", "unittest", "pydoc"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Limitless Sound", console=False,
          icon=str(ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")))
coll = COLLECT(exe, a.binaries, a.datas, name="Limitless Sound")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Limitless Sound.app", bundle_identifier="org.limitlesssound.hub",
                 icon=str(ROOT / "packaging" / "icon.icns"),
                 info_plist={"CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                             "LSUIElement": True, "NSHighResolutionCapable": True})
