"""The languages the suite can be set to, and the computer's own language.

A language is a lowercase BCP 47 primary tag. An app that supports the chosen language
listens and answers in it; the others carry on in English.
"""

from __future__ import annotations

import locale
import subprocess
import sys

# Each in its own name, so a person who reads only that language can find it.
LANGUAGES = {"en": "English", "es": "Español"}
DEFAULT = "en"


def tag(value) -> str | None:
    """'es', 'es-MX', 'es_ES.UTF-8' → 'es'; None when it isn't a language the suite has."""
    if not isinstance(value, str):
        return None
    primary = value.strip().replace("_", "-").split("-")[0].split(".")[0].lower()
    return primary if primary in LANGUAGES else None


def _mac_languages() -> list[str]:
    out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                         text=True, timeout=5).stdout
    return [p.strip().strip('",') for p in out.splitlines() if p.strip().strip('",()')]


def _windows_languages() -> list[str]:
    import ctypes
    lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    return [locale.windows_locale.get(lcid, "")]


def system_language(read=None) -> str:
    """The computer's first language that the suite has, or English."""
    try:
        if read is not None:
            found = read()
        elif sys.platform == "darwin":
            found = _mac_languages()
        elif sys.platform.startswith("win"):
            found = _windows_languages()
        else:
            found = [locale.getlocale()[0] or ""]
    except Exception:
        return DEFAULT
    for value in found:
        if tag(value):
            return tag(value)
    return DEFAULT
