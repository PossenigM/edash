from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import platformdirs

from edash.usb import USB_PID, USB_VID

# Receives "lock", "unlock", "suspend", "resume" or "shutdown". Called from a
# background thread; on suspend/shutdown the OS waits only briefly, so the
# callback should just send a message and return.
EventCallback = Callable[[str], None]


class EventWatcher(Protocol):
    def stop(self) -> None: ...


class Platform(ABC):
    name: str

    def config_dir(self) -> Path:
        return platformdirs.user_config_path("edash", appauthor=False)

    def cache_dir(self) -> Path:
        return platformdirs.user_cache_path("edash", appauthor=False)

    def log_dir(self) -> Path:
        return platformdirs.user_log_path("edash", appauthor=False)

    def default_config_path(self) -> Path:
        return self.config_dir() / "config.yaml"

    def token_cache_path(self) -> Path:
        return self.cache_dir() / "msal_token_cache.bin"

    def port_candidates(self) -> list[str]:
        """Serial ports that belong to an eDash gadget, most likely app port first.

        The gadget exposes two ports (app + debug console); the host probes them
        with a hello, so the order only has to be a good first guess.
        """
        from serial.tools import list_ports

        ports = [p for p in list_ports.comports() if p.vid == USB_VID and p.pid == USB_PID]
        ports.sort(key=self._port_sort_key)
        return [p.device for p in ports]

    def _port_sort_key(self, port: Any) -> tuple:
        return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", port.device))

    def token_persistence(self, path: Path):
        """Encrypted storage for the Microsoft login token (msal-extensions)."""
        from msal_extensions import build_encrypted_persistence

        path.parent.mkdir(parents=True, exist_ok=True)
        return build_encrypted_persistence(str(path))

    def start_event_watcher(self, callback: EventCallback) -> EventWatcher | None:
        """Report lock/sleep/shutdown events; None where unsupported."""
        return None

    @abstractmethod
    def install_autostart(self, config_path: Path) -> list[str]:
        """Start the host at login. Returns lines describing what was done or is left to do."""

    @abstractmethod
    def uninstall_autostart(self) -> list[str]: ...

    @abstractmethod
    def open_file(self, path: Path) -> None: ...
