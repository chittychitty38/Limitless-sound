"""Find the speech model, or download it if it isn't there.

Installers ship the small English model inside the app, so it works offline
from the first launch. If it's missing (running from source), we fetch it
once into the user's data folder.
"""

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .settings import data_dir

DEFAULT_MODEL = "vosk-model-small-en-us-0.15"
MODEL_URL = "https://alphacephei.com/vosk/models/{name}.zip"


def _models():
    from .language import available, load
    return {name: (m["label"], m["size"]) for code, _ in available() for name, m in load(code).models.items()}


# Models users can choose in Settings, for every language: name -> (label, download size).
# Each language's file lists its own (languages/<code>.yaml).
MODELS = _models()


def _search_dirs():
    dirs = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        dirs.append(Path(bundle) / "models")
    dirs.append(Path(__file__).resolve().parent.parent / "models")
    dirs.append(data_dir() / "models")
    return dirs


def find_model(name=DEFAULT_MODEL):
    for d in _search_dirs():
        candidate = d / name
        # Older models, like the Portuguese one, keep everything in one folder, with no am/ or conf/
        if (candidate / "am").is_dir() or (candidate / "conf").is_dir() or (candidate / "final.mdl").is_file():
            return candidate
    return None


def download_model(name=DEFAULT_MODEL, progress=None):
    """Download and unpack a model. progress(fraction) is called as it goes."""
    target_root = data_dir() / "models"
    target_root.mkdir(parents=True, exist_ok=True)
    url = MODEL_URL.format(name=name)
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / f"{name}.zip"
        with urllib.request.urlopen(url, timeout=30) as resp, open(zpath, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        src = Path(tmp) / name
        dest = target_root / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(src), str(dest))
    return dest
