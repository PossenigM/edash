from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from edash.host.platform.base import EventCallback, EventWatcher, Platform

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "eDash Host"


class WindowsPlatform(Platform):
    name = "windows"

    def _port_sort_key(self, port: Any) -> tuple:
        # COM3 before COM12; the app port is enumerated first in practice.
        digits = "".join(c for c in port.device if c.isdigit())
        return (int(digits) if digits else 0,)

    def start_event_watcher(self, callback: EventCallback) -> EventWatcher | None:
        from edash.host.platform.windows_events import WindowsEventWatcher

        return WindowsEventWatcher(callback).start()

    def install_autostart(self, config_path: Path) -> list[str]:
        # HKCU\...\Run needs no admin rights (unlike a logon task in Task Scheduler).
        import winreg

        command = subprocess.list2cmdline(
            [str(_gui_python()), "-m", "edash.host", "run", "--tray", "--config", str(config_path)]
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
        return [f"Added '{RUN_VALUE}' to HKCU\\{RUN_KEY}:", f"  {command}", "It starts at your next login."]

    def uninstall_autostart(self) -> list[str]:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            return ["Autostart was not installed."]
        return [f"Removed '{RUN_VALUE}' from HKCU\\{RUN_KEY}."]

    def open_file(self, path: Path) -> None:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only


def _gui_python() -> Path:
    """pythonw.exe runs without a console window."""
    exe = Path(sys.executable)
    windowed = exe.with_name("pythonw.exe")
    return windowed if windowed.exists() else exe
