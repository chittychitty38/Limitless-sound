"""Launcher used by PyInstaller (and handy from source: python run_app.py)."""

import sys

from limitless_voice.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
