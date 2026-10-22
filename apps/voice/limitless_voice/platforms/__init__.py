"""Operating-system layer: press keys, type text, find and open apps.

get_platform() returns the right implementation for this computer. Every
platform has the same methods, so the engine never needs to know which one
it's on.
"""

import sys


def current_os():
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def get_platform(dry_run=False, os_name=None):
    os_name = os_name or current_os()
    if dry_run:
        from .dryrun import DryRunPlatform
        return DryRunPlatform(os_name)
    if os_name == "mac":
        from .mac import MacPlatform
        return MacPlatform()
    if os_name == "windows":
        from .windows import WindowsPlatform
        return WindowsPlatform()
    from .linux import LinuxPlatform
    return LinuxPlatform()
