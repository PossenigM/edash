from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

import serial

from edash.device.app import DeviceApp
from edash.device.display import Display, FileDisplay


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="edash-device", description="eDash display service (runs on the Pi)")
    parser.add_argument("--port", default="/run/edash-tty", help="serial port or pyserial URL (default: %(default)s)")
    parser.add_argument("--display", choices=["waveshare", "file"], default="waveshare")
    parser.add_argument("--out", type=Path, default=Path("edash-frame.png"), help="PNG written by --display file")
    parser.add_argument("--log-level", default="INFO")
    test = parser.add_argument_group("self-test")
    test.add_argument("--selftest", action="store_true", help="show a test pattern and time refreshes, then exit")
    test.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], default=0, help="rotation to test")
    test.add_argument("--partial-steps", type=int, default=10)
    test.add_argument("--pause", type=float, default=1.0, help="seconds between test steps")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    display = _open_display(args)

    if args.selftest:
        from edash.device.selftest import run_selftest

        report = run_selftest(display, rotation=args.rotation, partial_steps=args.partial_steps, pause=args.pause)
        print(f"Self-test done: {report.summary()}")
        return

    def open_port():
        return serial.serial_for_url(args.port, baudrate=115200, timeout=1, write_timeout=2)

    app = DeviceApp(display, open_port)
    signal.signal(signal.SIGTERM, lambda *_: app.stop())
    try:
        app.run()
    except KeyboardInterrupt:
        app.stop()


def _open_display(args: argparse.Namespace) -> Display:
    if args.display == "file":
        return FileDisplay(args.out)
    from edash.device.display import WaveshareDisplay

    try:
        return WaveshareDisplay()
    except Exception as err:
        sys.exit(
            f"Cannot open the e-ink panel: {err}\n"
            "Is the edash-device service still running (sudo systemctl stop edash-device)? "
            "Is SPI enabled, and is this user in the spi and gpio groups?"
        )


if __name__ == "__main__":
    main()
