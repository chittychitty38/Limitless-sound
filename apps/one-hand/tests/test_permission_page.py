"""The macOS permission page, which checks the two privacy switches every second while it waits."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no windows pop up while testing

from PySide6.QtWidgets import QApplication  # noqa: E402

from onehand import app as app_module  # noqa: E402
from onehand import limitless_link  # noqa: E402
from onehand.platform_sim import SimBackend  # noqa: E402
from onehand.settings import Prefs, load_layouts  # noqa: E402


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITLESS_SOUND_HOME", str(tmp_path))
    monkeypatch.setattr(limitless_link, "launch_hub", lambda: False)
    monkeypatch.setattr(Prefs, "save", lambda self: None)
    QApplication.instance() or QApplication([])
    w = app_module.MainWindow(SimBackend(front_app="limitless.sim"), Prefs(), load_layouts())
    yield w.permission_page
    w.shutdown()


def test_waiting_restyles_nothing_until_a_switch_changes(page, monkeypatch):
    restyled = []
    monkeypatch.setattr(app_module, "repolish", restyled.append)
    names = list(page.steps)
    waiting = {name: False for name in names}

    page.refresh(waiting, False)
    first = len(restyled)
    assert first == len(names)
    for _ in range(5):                      # five more seconds of waiting
        page.refresh(dict(waiting), False)
    assert len(restyled) == first

    page.refresh({**waiting, names[0]: True}, False)   # the person switches one on
    assert len(restyled) == first + len(names)
    box, tick, btn = page.steps[names[0]]
    assert tick.text() == "✓" and btn.isHidden()
