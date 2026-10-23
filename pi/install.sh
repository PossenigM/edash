#!/bin/bash
# Installs the eDash display service on Raspberry Pi OS Lite (64-bit).
# Run on the Pi from a copy of this repository while it still has Wi-Fi:
#   sudo ./pi/install.sh
# Afterwards (and once everything works): sudo ./pi/lockdown.sh
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

REPO=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=/opt/edash
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot
WAVESHARE_REF=${WAVESHARE_REF:-master}
WAVESHARE_RAW="https://raw.githubusercontent.com/waveshareteam/e-Paper/${WAVESHARE_REF}/RaspberryPi_JetsonNano/python/lib/waveshare_epd"

echo "==> System packages"
apt-get update
apt-get install -y --no-install-recommends \
    python3-venv python3-pip python3-pil python3-spidev python3-gpiozero python3-lgpio \
    fonts-dejavu-core curl

echo "==> SPI and USB device mode"
raspi-config nonint do_spi 0
# Match the exact line: stock config.txt has "dtoverlay=dwc2,dr_mode=host" under [cm5].
if ! grep -q '^dtoverlay=dwc2,dr_mode=peripheral' "$BOOT/config.txt"; then
    printf '\n[all]\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$BOOT/config.txt"
fi
printf 'dwc2\nlibcomposite\n' > /etc/modules-load.d/edash.conf
if grep -q 'g_ether\|g_serial' "$BOOT/cmdline.txt"; then
    echo "WARNING: $BOOT/cmdline.txt loads g_ether/g_serial; remove that, it conflicts with the eDash gadget." >&2
fi

echo "==> Service user"
id edash >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin edash
usermod -aG spi,gpio,dialout edash

echo "==> Application"
install -d "$PREFIX/bin" "$PREFIX/vendor/waveshare_epd"
[ -d "$PREFIX/venv" ] || python3 -m venv --system-site-packages "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip
"$PREFIX/venv/bin/pip" install --upgrade "${REPO}[device]"

echo "==> Waveshare driver ($WAVESHARE_REF)"
for f in __init__.py epdconfig.py epd7in5_V2.py; do
    curl -fsSL "$WAVESHARE_RAW/$f" -o "$PREFIX/vendor/waveshare_epd/$f"
done
SITE=$("$PREFIX/venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
echo "$PREFIX/vendor" > "$SITE/edash-vendor.pth"

echo "==> systemd units"
install -m 755 "$REPO/pi/usb-gadget.sh" "$PREFIX/bin/usb-gadget.sh"
install -m 644 "$REPO"/pi/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable edash-gadget.service edash-device.service

echo
echo "Done. Reboot, then plug the Pi's USB data port (not PWR) into the laptop."
echo "Logs: journalctl -u edash-device -f"
