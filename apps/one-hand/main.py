import sys


def self_test():
    """Used by the installer builds: load everything and try the keyboard hook once."""
    from onehand.engine import Engine
    from onehand.platform_sim import get_backend
    from onehand.settings import load_layouts

    backend = get_backend()
    engine = Engine(load_layouts(), backend.platform)
    try:
        backend.start(engine)
        print(f"self-test: {backend.platform} keyboard hook started, front app = {backend.front_app()!r}")
        if hasattr(backend, "inject"):
            import time
            for _ in range(2):  # double-tap Shift through the real hook
                backend.inject("shift_l", up=False); time.sleep(0.05)
                backend.inject("shift_l", up=True); time.sleep(0.1)
            time.sleep(0.3)
            print(f"self-test: double-tap Shift turned one-hand mode {'ON' if engine.enabled else 'OFF'}")
            if not engine.enabled:
                return 1
        backend.stop()
    except Exception as exc:  # no permission on build machines is expected on macOS
        print(f"self-test: loaded, hook not started: {exc}")
        return 1 if backend.platform == "windows" else 0
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from onehand.app import main
    sys.exit(main())
