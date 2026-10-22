"""Builds Limitless-Sound-Suite-windows.exe: one Windows installer for the whole suite.

It carries each app's own installer and runs them one after another, quietly, for the
person signed in (no administrator needed), then turns on Limitless Sound so the apps
link up. Each app stays in Settings > Apps under its own name, so any one can be
removed or updated by itself.

  python packaging/windows/build_suite.py <downloads> <version> <output folder>

<downloads> holds one folder per app workflow (shared.yml, voice.yml, ...), each with
that app's Windows installer, as the suite workflow downloads them. Needs Inno Setup's
iscc on PATH. Standard library only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# In this order: the hub first, so every app finds it when it opens.
APPS = [
    ("shared.yml", "Limitless Sound", "/TASKS=startup"),
    ("voice.yml", "Limitless Voice", ""),
    ("one-hand.yml", "Limitless One-Hand", ""),
    ("zoom.yml", "Limitless Zoom", ""),
    ("color.yml", "Limitless Color", ""),
    ("control.yml", "Limitless Control", ""),
    ("gazestage.yml", "GazeStage", ""),
]
QUIET = {"inno": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-", "nsis": "/S"}


def kind(exe: Path) -> str | None:
    """Which installer maker built this, from the marker each leaves near the start of the file."""
    with exe.open("rb") as f:
        head = f.read(8 * 1024 * 1024)
    if b"Inno Setup" in head:
        return "inno"
    if b"Nullsoft" in head or b"NSIS" in head:
        return "nsis"
    return None


def find_installer(folder: Path) -> Path | None:
    exes = sorted(folder.rglob("*.exe"), key=lambda p: p.stat().st_size, reverse=True)
    return exes[0] if exes else None


def script(version: str, steps: list[tuple[Path, str, str]], out: Path) -> str:
    files = "\n".join(f'Source: "{exe}"; DestDir: "{{tmp}}"; DestName: "app{i}.exe"; Flags: deleteafterinstall'
                      for i, (exe, _, _) in enumerate(steps))
    runs = "\n".join(f'Filename: "{{tmp}}\\app{i}.exe"; Parameters: "{args}"; '
                     f'StatusMsg: "Installing {name}..."; Flags: waituntilterminated'
                     for i, (_, name, args) in enumerate(steps))
    return f"""; Made by packaging/windows/build_suite.py. Don't edit: run that instead.
[Setup]
AppId={{{{65445FF8-F6FA-4087-9987-32E0D03866EE}}
AppName=Limitless Sound
AppVersion={version}
AppVerName=Limitless Sound {version}, every app
AppPublisher=Limitless Sound
AppPublisherURL=https://chittychitty38.github.io/Limitless-sound/
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
DisableReadyPage=yes
OutputDir={out}
OutputBaseFilename=Limitless-Sound-Suite-windows
SetupIconFile={ROOT / "shared" / "hub" / "packaging" / "icon.ico"}
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern

[Messages]
WelcomeLabel2=This installs all six Limitless Sound apps (Voice, One-Hand, Zoom, Color, Control and GazeStage) and Limitless Sound, which joins them, so any input can trigger any app.%n%nIt takes a minute or two and doesn't need an administrator. Each app is listed in Settings > Apps under its own name.
FinishedLabelNoIcons=Limitless Sound is installed. It starts by itself when you sign in.%n%nThe first time you use an app, it asks for what it needs (the microphone or the camera) and says why.

[Files]
{files}

[Run]
{runs}
Filename: "{{userpf}}\\Limitless Sound\\Limitless Sound.exe"; Description: "Open Limitless Sound now"; Flags: nowait postinstall skipifsilent
"""


def main(argv=None) -> int:
    downloads, version, out = (Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])) if argv is None else argv
    out.mkdir(parents=True, exist_ok=True)
    steps, missing = [], []
    for folder, name, extra in APPS:
        exe = find_installer(downloads / folder)
        if exe is None:
            missing.append(name)
            continue
        k = kind(exe)
        if k is None:
            print(f"{name}: can't tell how to run {exe.name} quietly")
            return 1
        print(f"{name}: {exe.name} ({k})")
        steps.append((exe.resolve(), name, f"{QUIET[k]} {extra}".strip()))
    if missing:
        print("No Windows installer for: " + ", ".join(missing))
        return 1
    iss = out / "suite.iss"
    iss.write_text(script(version, steps, out.resolve()), encoding="utf-8-sig")
    return subprocess.run(["iscc", str(iss)]).returncode


if __name__ == "__main__":
    sys.exit(main())
