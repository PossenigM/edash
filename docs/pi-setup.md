# Pi setup

## Installation

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. Configure Wi-Fi
   and SSH for the initial setup.
2. Copy the repository to the Pi and run the installer:
   ```sh
   scp -r edash <user>@<host>:~/
   ssh <user>@<host>
   sudo bash ~/edash/pi/install.sh
   sudo reboot
   ```
   `install.sh`:
   - installs system packages and enables SPI
   - enables USB device mode (`dtoverlay=dwc2,dr_mode=peripheral`)
   - creates the `edash` service user and a venv in `/opt/edash`
   - downloads the Waveshare `epd7in5_V2` driver
   - installs and enables the systemd units
3. Run the [panel self-test](#panel-self-test).
4. Connect the Pi's **USB** port to the laptop. Check the service log:
   ```sh
   journalctl -u edash-device -f
   ```
5. Save a Wi-Fi network for debugging, if required (see [Wi-Fi](#wi-fi)).
6. Run `sudo bash ~/edash/pi/lockdown.sh` and reboot.

### Systemd units

| Unit | Function |
|---|---|
| `edash-gadget.service` | Creates the USB gadget (`pi/usb-gadget.sh`) |
| `edash-device.service` | Display service; reads `/run/edash-tty` |
| `edash-wifi-off.service` | Switches Wi-Fi off after boot; enabled by `lockdown.sh` |

### USB gadget

The gadget (`1d6b:0104`) exposes two CDC-ACM functions:

| Interface | Pi | Function |
|---|---|---|
| 0 | `/dev/ttyGS0` → `/run/edash-tty` | Application protocol |
| 2 | `/dev/ttyGS1` | Login console (`serial-getty`) |

Windows 10/11 and Linux bind their built-in CDC-ACM drivers. No driver installation
is required.

## Panel self-test

```sh
sudo systemctl stop edash-device
sudo -u edash /opt/edash/venv/bin/edash-device --selftest
sudo systemctl start edash-device
```

The self-test draws a test pattern with a full refresh, runs ten partial refreshes
with a moving square and finishes with a full refresh showing the measured timings.
The timings are also printed to the terminal.

| Element | Purpose |
|---|---|
| 1 px outer frame | Visible on all four sides if the panel does not crop |
| ▲ UP arrow | Points to the top of the enclosure; otherwise set `display.rotation` |
| 1/2/4/8 px checkerboards, font samples | Legibility of fine detail and small text |
| Moving square | Flicker and ghosting of partial refreshes |

Options: `--partial-steps N`, `--pause SECONDS`, `--rotation 0|90|180|270`.
`--display file --out selftest.png` writes the final frame to a PNG instead.

## Lockdown

`pi/lockdown.sh` prepares the Pi for unattended operation:

- Wi-Fi is switched off after every boot (`edash-wifi-off.service`)
- Bluetooth is disabled (`dtoverlay=disable-bt`)
- automatic updates, time sync, Avahi, ModemManager and swap are disabled; the host
  sets the clock
- the journal is kept in RAM (16 MB)
- the root file system is mounted read-only with an overlay (`raspi-config`)

Writes after lockdown go to RAM and are lost on reboot. Disconnecting the cable at
any time cannot corrupt the SD card.

## Debug console

The second serial port provides a login console at 115200 baud. It works without
network access.

Linux, with the udev rule from `edash-host install-autostart`:
```sh
python -m serial.tools.miniterm /dev/edash-console 115200
```
Windows: the second COM port, with PuTTY or `python -m serial.tools.miniterm COMx 115200`.

Press Enter to get the login prompt. `Ctrl+]` exits miniterm.

## Wi-Fi

After lockdown, Wi-Fi can be switched on from the debug console until the next boot:

```sh
sudo nmcli radio wifi on
nmcli -g IP4.ADDRESS device show wlan0
```

The Pi only joins networks saved before lockdown, as the read-only root discards
later changes. A network can be saved without being in range:

```sh
sudo nmcli connection add type wifi ifname wlan0 con-name hotspot ssid "<SSID>" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "<password>"
```

mDNS is disabled after lockdown, so `<host>.local` does not resolve. Use the IP address.

## Updates

1. Log in on the debug console and run `sudo bash ~/edash/pi/unlock.sh`, then reboot.
   The root file system is writable again and Wi-Fi is enabled.
2. Copy the new version to the Pi and run `sudo bash ~/edash/pi/install.sh`.
3. Run `sudo bash ~/edash/pi/lockdown.sh` and reboot.

## Troubleshooting

| Symptom | Check |
|---|---|
| `device descriptor read/64, error -71` on the host | Data cable, direct port without hub; power the Pi via PWR to rule out power issues |
| `/sys/kernel/config/usb_gadget/edash` missing | `grep dwc2 /boot/firmware/config.txt` must show `dtoverlay=dwc2,dr_mode=peripheral` under `[all]`; `ls /sys/class/udc` must not be empty |
| `Cannot open the e-ink panel` | `ls /dev/spidev0.*`, HAT seating, `journalctl -u edash-device` |
