"""Entry point.

  Limitless Voice (no arguments)   open the app
  ... do "solo track"              run one phrase and exit (for Voice Control,
                                   Shortcuts, Stream Deck, scripts)
  ... list                         print every phrase
  ... typed                        type phrases in the terminal instead of speaking
  add --dry-run to see what would happen without pressing anything
"""

import argparse
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # macOS passes -psn_... when launched from Finder; ignore anything like it
    argv = [a for a in argv if not a.startswith("-psn")]
    if not argv:
        from .app import run
        return run()

    from .engine import Engine
    from .grammar import DEFAULT_PACK_DIR, load_packs
    from .platforms import current_os, get_platform
    from .settings import user_packs_dir

    p = argparse.ArgumentParser(prog="limitless_voice", description="Voice control for music software")
    p.add_argument("mode", choices=["app", "do", "list", "typed"])
    p.add_argument("phrase", nargs="*", help='with "do": the phrase to run')
    p.add_argument("--dry-run", action="store_true", help="show what would run, don't press anything")
    p.add_argument("--app", help="with --dry-run: pretend this app is in front (e.g. 'Logic Pro')")
    p.add_argument("--os", choices=["mac", "windows", "linux"], help="with --dry-run: pretend to be this OS")
    args = p.parse_args(argv)

    if args.mode == "app":
        from .app import run
        return run()

    os_name = args.os or current_os()
    packs = load_packs([DEFAULT_PACK_DIR, user_packs_dir()], os_name)

    if args.mode == "list":
        for pack in packs:
            scope = ", ".join(pack.apps) or "every app"
            print(f"\n== {pack.name} ({scope}) ==")
            for c in pack.commands:
                print(f"  {' | '.join(c.phrases)}")
        return 0

    if args.dry_run:
        from .platforms.dryrun import DryRunPlatform
        platform = DryRunPlatform(os_name, echo=True, app=args.app)
    else:
        platform = get_platform()
    engine = Engine(platform, packs, feedback=lambda m: None)

    if args.mode == "do":
        r = engine.handle(" ".join(args.phrase))
        print(r.message)
        return 0 if r.handled else 1

    while True:  # typed
        try:
            line = input("say> ")
        except (EOFError, KeyboardInterrupt):
            return 0
        if not line.strip():
            continue
        try:
            r = engine.handle(line)
        except Exception as e:
            print(f"  ! {e}")
            continue
        if r.message and r.message != "asleep":
            print(("✓ " if r.handled else "? ") + r.message)


if __name__ == "__main__":
    sys.exit(main())
