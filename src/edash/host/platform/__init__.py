"""Everything OS-specific on the host sits behind :class:`Platform`."""

from __future__ import annotations

import sys

from edash.host.platform.base import Platform


def get_platform() -> Platform:
    if sys.platform == "win32":
        from edash.host.platform.windows import WindowsPlatform

        return WindowsPlatform()
    if sys.platform.startswith("linux"):
        from edash.host.platform.linux import LinuxPlatform

        return LinuxPlatform()
    raise RuntimeError(f"unsupported host platform: {sys.platform}")


__all__ = ["Platform", "get_platform"]
