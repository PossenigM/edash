from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from edash.host.platform.base import EventCallback, EventWatcher, Platform
from edash.usb import USB_MANUFACTURER, USB_PID, USB_VID

log = logging.getLogger(__name__)

UNIT_NAME = "edash-host.service"
UDEV_RULE_NAME = "70-edash.rules"  # must sort before 73-seat-late.rules for TAG+="uaccess"
STABLE_PORT = Path("/dev/edash")


def udev_rule() -> str:
    match = (
        f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{USB_VID:04x}", ATTRS{{idProduct}}=="{USB_PID:04x}", '
        f'ATTRS{{manufacturer}}=="{USB_MANUFACTURER}"'
    )
    return "\n".join(
        [
            "# eDash display (Raspberry Pi USB gadget), written by `edash-host install-autostart`.",
            "# Keep ModemManager away from it, give the logged-in user access, and add stable names.",
            f'{match}, ENV{{ID_MM_DEVICE_IGNORE}}="1", TAG+="uaccess"',
            f'{match}, ENV{{ID_USB_INTERFACE_NUM}}=="00", SYMLINK+="edash"',
            f'{match}, ENV{{ID_USB_INTERFACE_NUM}}=="02", SYMLINK+="edash-console"',
            "",
        ]
    )


def systemd_unit(config_path: Path) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=eDash host (feeds the e-ink dashboard over USB)",
            "",
            "[Service]",
            f"ExecStart={sys.executable} -m edash.host run --config {config_path}",
            "Restart=on-failure",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


class LinuxPlatform(Platform):
    name = "linux"

    def port_candidates(self) -> list[str]:
        if STABLE_PORT.exists():  # created by the udev rule; always the app port
            return [str(STABLE_PORT)]
        return super().port_candidates()

    def _port_sort_key(self, port: Any) -> tuple:
        # location looks like "1-2:1.0"; the app function is interface 0.
        interface = (port.location or "").rpartition(".")[2]
        return (int(interface) if interface.isdigit() else 99, port.device)

    def token_persistence(self, path: Path):
        try:
            return super().token_persistence(path)
        except Exception as err:
            from msal_extensions import FilePersistence

            log.warning(
                "no Secret Service keyring available (%s); storing the login token unencrypted in %s "
                "(install PyGObject + gnome-keyring or KWallet to avoid this)",
                err,
                path,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600, exist_ok=True)
            os.chmod(path, 0o600)
            return FilePersistence(str(path))

    def start_event_watcher(self, callback: EventCallback) -> EventWatcher | None:
        from edash.host.platform.logind import LogindWatcher

        return LogindWatcher(callback).start()

    def install_autostart(self, config_path: Path) -> list[str]:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / UNIT_NAME).write_text(systemd_unit(config_path))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", UNIT_NAME], check=True)

        rule_file = self.cache_dir() / UDEV_RULE_NAME
        rule_file.parent.mkdir(parents=True, exist_ok=True)
        rule_file.write_text(udev_rule())
        return [
            f"Enabled systemd user service {UNIT_NAME} (logs: journalctl --user -u {UNIT_NAME} -f).",
            "Install the udev rule once (needs root):",
            f"  sudo install -m 644 {rule_file} /etc/udev/rules.d/{UDEV_RULE_NAME}",
            "  sudo udevadm control --reload && sudo udevadm trigger",
            "For the tray icon, start `edash-host run --tray` from your desktop's autostart instead.",
        ]

    def uninstall_autostart(self) -> list[str]:
        subprocess.run(["systemctl", "--user", "disable", "--now", UNIT_NAME], check=False)
        (Path.home() / ".config" / "systemd" / "user" / UNIT_NAME).unlink(missing_ok=True)
        return [f"Disabled and removed {UNIT_NAME}.", f"Remove /etc/udev/rules.d/{UDEV_RULE_NAME} manually if wanted."]

    def open_file(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path)])
