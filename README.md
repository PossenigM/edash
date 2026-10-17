# eDash

An e-ink office dashboard: a Raspberry Pi Zero 2W with a Waveshare 7.5" (V2,
800×480, black/white) panel, connected to the work laptop by one USB cable.
The cable powers the Pi and carries the data, so it needs no Wi-Fi.

```
Laptop: edash-host                          USB serial (CDC-ACM)         Pi: edash-device
  config.yaml ─┐                         ─── config, time, data ──►        state (RAM only)
  Graph (mail, calendar, Teams chats)    ◄── hello, acks, errors ──        screen rules
  Open-Meteo (weather)                                                     renderer + widgets
  tray / `edash-host ctl`                                                  e-ink driver
```

The layout lives in one YAML file on the laptop. The host pushes it to the Pi
whenever you save it. The Pi renders everything itself, so the clock and
reminders keep running between data updates. Renderer and widgets are shared
code, so `edash-host preview` shows exactly what the panel will show.

## Repository layout

| Path | What |
|---|---|
| `src/edash/config.py` | Config schema (pydantic). `assets/config.example.yaml` documents every option |
| `src/edash/protocol.py`, `link.py` | JSON-lines messages and the reconnecting serial link |
| `src/edash/render/` | Layout grid, fonts, icons, renderer, preview, sample data |
| `src/edash/render/widgets/` | One module per widget |
| `src/edash/rules.py` | Condition language for screen rotation |
| `src/edash/device/` | Pi service: main loop, refresh policy, clock sync, panel driver |
| `src/edash/host/` | Laptop service: sources, Graph login, control socket, tray, CLI |
| `src/edash/host/platform/` | Everything OS-specific (Windows / Linux) |
| `pi/` | Pi setup: USB gadget, install, lockdown/unlock, systemd units |

## Quick start (no hardware needed)

```sh
python -m venv ~/.venvs/edash            # keep venvs out of synced folders (Nextcloud!)
~/.venvs/edash/bin/pip install -e ".[host,dev]"
edash-host preview --scale 2              # renders preview-<screen>.png with sample data
edash-host preview --at 2026-10-19T16:50 --screen main
pytest
```

## Configuration

`edash-host init-config` copies the example to your per-user config directory
(`%APPDATA%\edash\config.yaml` on Windows, `~/.config/edash/config.yaml` on
Linux). `edash-host check` validates it. Errors name the exact place, e.g.
`screen 'main', widget 2 (reminder): options.every: invalid duration 'soon'`.

- **Screens**: each has an `id` and a list of widgets.
- **Placement**: `pos: [col, row]` + `size: [cols, rows]` on the grid (`display.grid`, default 12×8), or `box: [x, y, w, h]` in pixels.
- **Per widget**: `title`, `frame: true`, and widget-specific `options` (unknown keys are errors).
- **Rotation**: the first matching rule wins, otherwise `default`. Example: `meeting_starts_in <= 5m`, `time in 18:30-07:00 and not meeting_active`.

### Language

`display.language: de` (or `en`) switches day and month names and all
display texts ("7 ungelesen", "Heute", "bis 10:00", "Stand 16:25", …). Names
are built in, so the Pi's system locale doesn't matter. `%A`, `%a`, `%B` and
`%b` in your own `date_format` follow the setting too. To add a language,
copy the `EN` block in `src/edash/render/i18n.py`. A test checks that every
language has the same keys.

### Away screen

When you lock the laptop, it goes to sleep, shuts down or the host stops, the
display switches to an away screen. It shows the reason, the time and your
next meeting. It has no clock on purpose: the Pi may lose power along with
the laptop, and a frozen clock would show the wrong time. Unlocking or
resuming switches back. Set `rotation.away_screen` to use one of your own
screens instead (the `away` widget is available there too).

- **Windows**: a hidden window receives lock/unlock, sleep/resume and shutdown messages. Windows allows only about 2 s at suspend; locking first (Win+L) gives the panel more time.
- **Linux**: events come from systemd-logind (D-Bus, via `jeepney`). The host holds a logind delay lock, so suspend/shutdown waits up to 4 s for the away frame.

If USB power drops in the middle of a refresh, the panel may show a partly drawn frame until the next start.

### Outdated data

The host stamps every fetch with `fetched_at` and `fresh_until`: three poll
intervals, but at least 10 minutes. If a source stops updating (login expired,
network gone), the widget gets an inverted **"as of 09:12"** label in its title
bar or top-right corner. A fresh fetch removes it. Turn it off per widget with
`show_stale: false`.

### Widgets

| Type | Shows | Main options |
|---|---|---|
| `clock` | Time and date | `time_format`, `date_format` (strftime), `date_ratio` |
| `weather` | Current conditions + forecast | `days`, `show_location` |
| `calendar` | Agenda; the running meeting inverted | `days`, `max_items`, `font_size`, `show_location`, `show_past` |
| `next_meeting` | Running/next meeting with countdown | `lookahead` |
| `mail` | Unread mails | `max_items`, `font_size`, `show_header` |
| `teams` | Recent chats, unread marked | `max_items`, `unread_only` |
| `reminder` | Recurring reminder, inverted when due | `label`, `every`, `active`, `days`, `highlight_for`, `icon` |
| `text` | Static text | `text`, `size`, `bold`, `align`, `invert` |
| `status` | Laptop connection, last update | `font_size`, `align` |
| `away` | Away reason, time, next meeting (for custom away screens) | `title`, `message`, `show_next_meeting` |

Icons for reminders: `drop`, `stand`, `eye`, `mail`, `chat`, `calendar`, `sun`, ….

### Adding a widget

Create `src/edash/render/widgets/<name>.py`, subclass `Widget`, declare an
`Options` model, decorate with `@widget("<name>")` and import it in
`widgets/__init__.py`. Draw relative to `ctx.box` (your own canvas). Return the
time of your next visual change from `next_update`. Rendering errors are
caught and shown inside the widget's box, so one widget can't break the screen.

## Microsoft Graph (mail, calendar, Teams)

New Outlook has no COM interface, so the host uses Graph with **delegated,
read-only** permissions: `User.Read`, `Mail.Read`, `Calendars.Read`, `Chat.Read`.

1. **Check consent first**: sign in to Microsoft's Graph Explorer with your work account and run `GET /me/messages`. If you see "Need admin approval", ask IT to approve the four permissions above.
2. **Register an app**: Entra admin center → App registrations → New registration.
   - Single tenant.
   - Platform "Mobile and desktop applications", redirect URI `http://localhost`.
   - Under Authentication, enable "Allow public client flows" (needed for `--device-code`).
   - Add the four delegated permissions.
3. Put the Application (client) ID into `sources.graph.client_id`.
4. Run `edash-host login` (or `login --device-code`). The token is cached encrypted: DPAPI on Windows, Secret Service on Linux.

Teams channel posts would need `ChannelMessage.Read.All`, which always requires
admin consent, so only chats are supported.

## Laptop setup

**Windows**
```powershell
pip install "edash[host,tray] @ file:///C:/path/to/edash"   # or: uv tool install ".[host,tray]"
edash-host init-config ; notepad $env:APPDATA\edash\config.yaml
edash-host login
edash-host install-autostart        # HKCU Run key, no admin rights needed
```
The Pi shows up as two "USB Serial Device (COMx)" ports. The host finds the
app port by sending a hello on each one (`edash-host ports` lists candidates).

**Linux**: `edash-host install-autostart` enables a systemd user service. It
also writes a udev rule and prints the `sudo` command to install it. The rule
adds `/dev/edash`, gives your user access (`uaccess`), and stops
ModemManager from probing the port. Without a keyring, the login token falls
back to a file readable only by you, and the host logs a warning.

`edash-host ctl screen meeting|auto`, `ctl refresh`, `ctl fetch`, `ctl status`
control a running host. The tray menu offers the same commands.

Only one host runs at a time: a second `edash-host run` exits with a message,
because the control port (127.0.0.1:47811, `host.control_port`) is taken. If
Graph throttles requests (HTTP 429/503), the source waits as long as Graph's
`Retry-After` header says before polling again. `ctl status` shows this.

## Pi setup

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. Set up your home Wi-Fi and SSH for the initial setup.
2. Copy this repo to the Pi and run `sudo ./pi/install.sh`. It:
   - installs packages and enables SPI;
   - configures USB device mode (`dwc2`);
   - creates the `edash` user and a venv in `/opt/edash`;
   - downloads Waveshare's `epd7in5_V2` driver;
   - installs the systemd units.
3. Reboot and run the **panel self-test** (see below) before connecting anything else.
4. Plug the Pi's **USB** port (not PWR) into the laptop. Check with `journalctl -u edash-device -f`.
5. Once everything works, run `sudo ./pi/lockdown.sh`. It disables Wi-Fi/Bluetooth and network services, keeps logs in RAM, and makes the root filesystem read-only (overlayfs), so pulling the cable can't corrupt the SD card.
6. **Updates**: log in on the debug console (the second serial port, 115200 baud) and run `sudo ./pi/unlock.sh`, then reboot, update and run `lockdown.sh` again.

### Panel self-test

```sh
sudo systemctl stop edash-device                 # the service holds SPI/GPIO
sudo -u edash /opt/edash/venv/bin/edash-device --selftest
sudo systemctl start edash-device
```

This draws a test pattern (full refresh), runs 10 partial refreshes with a
moving square, then does a final full refresh showing the measured timings.
The timings are also printed to the terminal. What to check:

- **Panel works**: if nothing appears, check the HAT seating, SPI (`ls /dev/spidev0.*`) and the error message.
- **Edges**: the 1 px outer frame should be visible on all four sides.
- **Orientation**: the ▲ UP arrow points to the top of your enclosure. If not, try `--rotation 90|180|270` and put the value that works into `display.rotation`.
- **Detail and text**: how the 1/2/4/8 px checkerboards and the font samples look. This decides font sizes in your layout.
- **Partial refresh**: whether the square moves without flashing and what ghosting it leaves. Tune `full_refresh_every` / `max_partial_refreshes` from that.

Options: `--partial-steps N`, `--pause SECONDS`, `--rotation DEG`. On a
desktop, `--display file --out selftest.png` writes the final frame to a PNG.

Run the device on a desktop with a virtual serial pair:
```sh
socat pty,raw,echo=0,link=/tmp/edash-dev pty,raw,echo=0,link=/tmp/edash-host &
edash-device --port /tmp/edash-dev --display file --out frame.png &
edash-host run --config my-config.yaml     # with host.port: /tmp/edash-host
```

## Development

`pytest` runs the suite. CI (`.github/workflows/ci.yml`) runs on every push:

- the tests on Windows and Ubuntu with Python 3.11 and 3.13;
- the example config check;
- preview and self-test rendering, uploaded as a `previews` artifact;
- `bash -n` + ShellCheck on the Pi scripts.

## Needs verification on real hardware

- Partial refresh: `WaveshareDisplay` keeps the panel in partial mode between updates and sends full frames to `display_Partial`. Check for ghosting and tune `full_refresh_every` / `max_partial_refreshes`.
- Rotation (`display.rotation`): find the right value with the self-test's UP arrow.
- Composite gadget enumeration on your laptop (two COM ports appear without driver prompts).
- Graph queries against your tenant, especially Teams unread detection (`viewpoint.lastMessageReadDateTime`).
- Away screen timing: whether the frame finishes before your laptop cuts USB power on sleep/shutdown. The Windows event window is covered by a test that only runs on Windows (CI or your laptop).
