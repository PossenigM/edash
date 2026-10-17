#!/bin/bash
# USB gadget for the eDash Pi: two CDC-ACM serial ports over the USB data port.
#   port 1 (interface 0): app protocol  -> symlinked to /run/edash-tty
#   port 2 (interface 2): login console -> serial-getty, for debugging without network
# Windows 10/11 and Linux bind their built-in CDC-ACM drivers; no driver install needed.
#
# Usage: usb-gadget.sh up|down   (run by edash-gadget.service)
set -euo pipefail

G=/sys/kernel/config/usb_gadget/edash

# Keep in sync with src/edash/usb.py
VID=0x1d6b          # Linux Foundation
PID=0x0104          # Multifunction Composite Gadget
MANUFACTURER="eDash"
PRODUCT="eDash Display"
SERIAL="edash-$(tr -d '\0' < /sys/firmware/devicetree/base/serial-number 2>/dev/null | tail -c 8 || echo 0000)"

up() {
    modprobe libcomposite
    mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
    [ -d "$G" ] && down

    mkdir -p "$G"
    cd "$G"
    echo "$VID" > idVendor
    echo "$PID" > idProduct
    echo 0x0100 > bcdDevice
    echo 0x0200 > bcdUSB
    # Composite device with interface association descriptors, so Windows
    # binds usbser.sys to each ACM function.
    echo 0xEF > bDeviceClass
    echo 0x02 > bDeviceSubClass
    echo 0x01 > bDeviceProtocol

    mkdir -p strings/0x409
    echo "$SERIAL" > strings/0x409/serialnumber
    echo "$MANUFACTURER" > strings/0x409/manufacturer
    echo "$PRODUCT" > strings/0x409/product

    mkdir -p configs/c.1/strings/0x409
    echo "eDash serial" > configs/c.1/strings/0x409/configuration
    echo 250 > configs/c.1/MaxPower   # x2 mA = 500 mA

    mkdir -p functions/acm.app functions/acm.console
    ln -s functions/acm.app configs/c.1/
    ln -s functions/acm.console configs/c.1/

    ls /sys/class/udc | head -n 1 > UDC

    app_port=$(cat functions/acm.app/port_num)
    console_port=$(cat functions/acm.console/port_num)
    ln -sf "/dev/ttyGS${app_port}" /run/edash-tty
    systemctl --no-block start "serial-getty@ttyGS${console_port}.service"
}

down() {
    [ -d "$G" ] || return 0
    cd "$G"
    echo "" > UDC 2>/dev/null || true
    rm -f configs/c.1/acm.app configs/c.1/acm.console
    rmdir configs/c.1/strings/0x409 configs/c.1 2>/dev/null || true
    rmdir functions/acm.app functions/acm.console 2>/dev/null || true
    rmdir strings/0x409 2>/dev/null || true
    cd /
    rmdir "$G"
    rm -f /run/edash-tty
}

case "${1:-}" in
    up) up ;;
    down) down ;;
    *) echo "usage: $0 up|down" >&2; exit 2 ;;
esac
