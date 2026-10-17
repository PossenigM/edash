#!/bin/bash
# Prepares the Pi for the office: no radios, nothing that expects a network,
# logs in RAM, and a read-only root filesystem so pulling the USB cable at any
# time cannot corrupt the SD card. Undo with ./pi/unlock.sh.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

echo "==> Disable Wi-Fi and Bluetooth"
for overlay in disable-wifi disable-bt; do
    grep -q "^dtoverlay=$overlay\$" "$BOOT/config.txt" || echo "dtoverlay=$overlay" >> "$BOOT/config.txt"
done

echo "==> Disable services that need a network or unused hardware"
for unit in hciuart.service bluetooth.service apt-daily.timer apt-daily-upgrade.timer man-db.timer \
            systemd-timesyncd.service avahi-daemon.service avahi-daemon.socket ModemManager.service \
            dphys-swapfile.service; do
    systemctl disable --now "$unit" 2>/dev/null || true
done

echo "==> Keep logs in RAM"
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=16M\n' > /etc/systemd/journald.conf.d/edash.conf

echo "==> Enable read-only root (overlayfs)"
raspi-config nonint do_overlayfs 0

echo
echo "Done. Reboot to apply. Debug console: the second serial port on the laptop (115200 baud)."
