# Development

## Repository layout

| Path | Content |
|---|---|
| `src/edash/config.py` | Configuration schema (pydantic) |
| `src/edash/protocol.py`, `link.py` | JSON-lines messages and the reconnecting serial link |
| `src/edash/rules.py` | Condition language for screen rotation |
| `src/edash/render/` | Layout grid, fonts, icons, text fitting, renderer, preview, sample data |
| `src/edash/render/widgets/` | One module per widget |
| `src/edash/device/` | Pi service: main loop, refresh policy, clock, panel driver, self-test |
| `src/edash/host/` | Host service: data sources, Graph client, control port, tray, CLI |
| `src/edash/host/platform/` | OS-specific code for Windows and Linux |
| `src/edash/host/editor/` | Layout editor: local HTTP server and browser UI |
| `pi/` | Pi installation, USB gadget, lockdown, systemd units |
| `tests/` | pytest suite |

## Setup

```sh
python -m venv .venv
.venv/bin/pip install -e ".[host,dev]"
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests
```

CI runs on every push:

- tests on Ubuntu and Windows with Python 3.11 and 3.13
- `ruff check` and `ruff format --check`
- validation of the example configuration
- rendering of the example screens and the self-test frame, uploaded as the `previews` artifact
- `bash -n` and ShellCheck on `pi/*.sh`

## Protocol

Host and device exchange one JSON object per line at 115200 baud.

| Direction | Messages |
|---|---|
| Host → device | `hello`, `time`, `config`, `mail`, `calendar`, `teams`, `weather`, `presence`, `command` |
| Device → host | `hello`, `ack`, `error`, `status` |

The host sends its full snapshot after every `hello` from the device. All messages
are idempotent, and the device keeps no persistent state. Unknown fields are ignored.
`PROTOCOL_VERSION` in `src/edash/__init__.py` is increased on incompatible changes.

## Running the device on a desktop

A virtual serial pair connects host and device without hardware:

```sh
socat pty,raw,echo=0,link=/tmp/edash-dev pty,raw,echo=0,link=/tmp/edash-host &
edash-device --port /tmp/edash-dev --display file --out frame.png &
edash-host run --config my-config.yaml     # with host.port: /tmp/edash-host
```

## Adding a widget

1. Create `src/edash/render/widgets/<name>.py`.
2. Subclass `Widget`, declare an `Options` model derived from `WidgetOptions` and
   register the class with `@widget("<name>")`.
3. Import the module in `src/edash/render/widgets/__init__.py`.

`render()` draws relative to `ctx.box`. `next_update()` returns the time of the next
visual change without new data, or `None`. Exceptions during rendering are drawn
inside the widget's box and do not affect other widgets.

## Adding a language

Copy the `EN` locale in `src/edash/render/i18n.py`, add it to `LOCALES` and add the
language code to `DisplayConfig.language`. A test checks that all languages define
the same keys.
