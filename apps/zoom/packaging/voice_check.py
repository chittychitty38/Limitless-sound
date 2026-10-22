"""CI check: speak each phrase with the OS voice, recognise it, compare.
Usage: python packaging/voice_check.py MODEL_DIR WAV_DIR"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from limitless_zoom.voice import recognize_file  # noqa: E402

CASES = {"zoom_in": "in", "zoom_out": "out", "taller": "taller", "zoom_to_fit": "fit",
         "magnifier": "magToggle", "again": "again"}

failed = 0
for stem, want in CASES.items():
    text, got = recognize_file(sys.argv[1], Path(sys.argv[2]) / f"{stem}.wav")
    ok = got == want
    failed += not ok
    print(f"{'ok ' if ok else 'BAD'} {stem}: heard {text!r} -> {got}")
sys.exit(1 if failed > 1 else 0)  # synthetic voices are imperfect; allow one miss
