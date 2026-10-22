import sys
import time


def self_test():
    """Used by the installer builds: load everything and drive the real keyboard hook."""
    from onehand.engine import Engine
    from onehand.platform_sim import get_backend
    from onehand.settings import load_layouts

    backend = get_backend()
    engine = Engine(load_layouts(), backend.platform)
    try:
        backend.start(engine)
    except Exception as exc:  # macOS build machines may not grant keyboard access
        print(f"self-test: loaded, hook not started: {exc}")
        return 1 if backend.platform == "windows" else 0
    front = backend.front_app()
    print(f"self-test: {backend.platform} keyboard hook started, front app = {front!r}")
    failed = False

    if backend.platform == "windows":
        for _ in range(2):  # double-tap Shift through the real hook
            backend.inject("shift_l", up=False); time.sleep(0.05)
            backend.inject("shift_l", up=True); time.sleep(0.1)
        time.sleep(0.3)
        print(f"self-test: double-tap Shift turned one-hand mode {'ON' if engine.enabled else 'OFF'}")
        failed |= not engine.enabled

    # A practice press: the hook must see the key, ask the engine, and swallow it.
    engine.set_enabled(True)
    engine.self_app_ids = {(front or "").lower()}
    engine.preview_app = "protools"
    backend.inject("e", up=False); time.sleep(0.05)
    backend.inject("e", up=True); time.sleep(0.3)
    print(f"self-test: practice press seen = {engine.last_preview}")
    if backend.platform == "windows":
        failed |= engine.last_preview != ("e", "Record")
    backend.stop()
    return 1 if failed else 0


def ui_smoke():
    """Open the real window, menu bar icon and badge for a moment, switch the mode, and close."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from onehand.app import MainWindow
    from onehand.platform_sim import get_backend
    from onehand.settings import Prefs, load_layouts

    app = QApplication(sys.argv)
    win = MainWindow(get_backend(), Prefs(), load_layouts())
    win.show()
    steps = [lambda: win.engine.set_enabled(True), lambda: win.set_hand("right"),
             lambda: win.set_hand("left"), lambda: win.engine.set_enabled(False), win.quit]
    for i, step in enumerate(steps):
        QTimer.singleShot(400 * (i + 1), step)
    code = app.exec()
    print(f"ui-smoke: window ran, page {win.pages.currentIndex()}, tray {'yes' if win.tray else 'no'}")
    return code


if __name__ == "__main__":
    if "--self-test" in sys.argv or "--ui-smoke" in sys.argv:
        import faulthandler
        if sys.stderr is not None:   # a windowed Windows build has no stderr
            faulthandler.enable()    # print where it was if a native crash ever happens
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--ui-smoke" in sys.argv:
        sys.exit(ui_smoke())
    from onehand.app import main
    sys.exit(main())
