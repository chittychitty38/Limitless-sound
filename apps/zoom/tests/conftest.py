import pytest

from limitless_zoom import words


@pytest.fixture(autouse=True)
def english_computer(monkeypatch):
    """Every test starts in English with no hub, whatever this computer's language is.
    A test picks Spanish with words._computer (the computer's) or a hub's prefs (the suite's)."""
    monkeypatch.setattr(words, "_computer", "en")
    monkeypatch.setattr(words, "_suite", None)
    monkeypatch.setattr(words, "_shown", {})
