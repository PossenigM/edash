#!/bin/bash
# Reverses the parts of lockdown.sh that block updates: turns the read-only
# overlay off and Wi-Fi back on (after a reboot). Run from the debug console.
# Then update with `git pull && sudo ./pi/install.sh` and run lockdown.sh again.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

mount -o remount,rw "$BOOT" 2>/dev/null || true
raspi-config nonint do_overlayfs 1
sed -i '/^dtoverlay=disable-wifi$/d; /^dtoverlay=disable-bt$/d' "$BOOT/config.txt"

echo "Done. Reboot: root is writable again and Wi-Fi is back."
