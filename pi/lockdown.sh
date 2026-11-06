#!/bin/bash
# Prepares the Pi for the office: Wi-Fi off unless switched on for debugging,
# no Bluetooth, nothing that expects a network, logs in RAM, and a read-only
# root filesystem so pulling the USB cable at any time cannot corrupt the SD
# card. Undo with ./pi/unlock.sh.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

echo "==> Disable Bluetooth"
grep -q '^dtoverlay=disable-bt$' "$BOOT/config.txt" || echo "dtoverlay=disable-bt" >> "$BOOT/config.txt"

echo "==> Wi-Fi off after every boot (on for debugging: sudo nmcli radio wifi on)"
[ -f /etc/systemd/system/edash-wifi-off.service ] || {
    echo "edash-wifi-off.service is missing: run ./pi/install.sh first." >&2; exit 1; }
sed -i '/^dtoverlay=disable-wifi$/d' "$BOOT/config.txt"   # older lockdown.sh removed Wi-Fi entirely
systemctl enable edash-wifi-off.service

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
wifi=$(nmcli -t -f NAME,TYPE connection show | awk -F: '$2 == "802-11-wireless" { print "    " $1 }')
if [ -n "$wifi" ]; then
    printf 'Saved Wi-Fi networks (joined when Wi-Fi is switched on):\n%s\n' "$wifi"
else
    echo "No Wi-Fi network saved: switching Wi-Fi on will not connect anywhere."
fi
echo "Done. Reboot to apply. Debug console: the second serial port on the laptop (115200 baud)."
