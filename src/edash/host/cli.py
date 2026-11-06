from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import shutil
import signal
import socket
import sys
from datetime import datetime
from pathlib import Path

from edash.config import EXAMPLE_CONFIG, load_config
from edash.errors import ConfigError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="edash-host", description="eDash host: feeds the e-ink dashboard")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_config(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--config", type=Path, help="config file (default: per-user config dir)")
        return p

    p = with_config(sub.add_parser("run", help="run the host (connects to the display, polls sources)"))
    p.add_argument("--tray", action="store_true", help="show a tray icon")
    p.add_argument("--demo", action="store_true", help="sample mail/calendar/Teams data instead of Microsoft 365")

    p = with_config(sub.add_parser("preview", help="render screens with sample data to PNG files"))
    p.add_argument("--screen", action="append", help="screen id (repeatable; default: all)")
    p.add_argument("--out", type=Path, default=Path("."), help="output directory")
    p.add_argument("--scale", type=int, default=1, help="integer upscaling for easier viewing")
    p.add_argument("--at", help="render as if it were this local time, e.g. 2026-10-19T09:40")

    p = with_config(sub.add_parser("edit", help="open the layout editor in the browser"))
    p.add_argument("--port", type=int, default=0, help="local port (default: any free port)")
    p.add_argument("--no-browser", action="store_true", help="only print the URL")

    with_config(sub.add_parser("check", help="validate the config"))
    p = with_config(sub.add_parser("init-config", help="copy the example config to the config dir"))
    p.add_argument("--force", action="store_true")

    p = with_config(sub.add_parser("login", help="sign in to Microsoft 365 (Graph)"))
    p.add_argument("--device-code", action="store_true", help="sign in on another device (no local browser)")

    sub.add_parser("ports", help="list serial ports that look like an eDash")

    p = with_config(sub.add_parser("ctl", help="control a running host"))
    p.add_argument("action", choices=["screen", "refresh", "fetch", "reload", "status"])
    p.add_argument("arg", nargs="?", help="screen id or 'auto' (for 'screen')")

    with_config(sub.add_parser("install-autostart", help="start the host at login"))
    sub.add_parser("uninstall-autostart", help="remove the login autostart")

    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        COMMANDS[args.command](args)
    except ConfigError as err:
        sys.exit(str(err))


def _platform():
    from edash.host.platform import get_platform

    return get_platform()


def _config_path(args: argparse.Namespace, *, allow_example: bool = False) -> Path:
    if getattr(args, "config", None):
        return args.config
    path = _platform().default_config_path()
    if path.exists() or not allow_example:
        return path
    print(f"No config at {path} yet, using the bundled example (run `edash-host init-config`).", file=sys.stderr)
    return EXAMPLE_CONFIG


def _require_config(path: Path) -> None:
    if not path.exists():
        sys.exit(f"Config {path} not found. Create it with `edash-host init-config`.")


def cmd_run(args: argparse.Namespace) -> None:
    from edash.host.app import AlreadyRunning, HostApp

    platform = _platform()
    path = _config_path(args)
    _require_config(path)
    log_dir = platform.log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "host.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    app = HostApp(path, platform, demo=args.demo)
    try:
        app.open_control_server()
    except AlreadyRunning as err:
        sys.exit(str(err))
    # systemd stops the service with SIGTERM; exit through run()'s cleanup so the away screen goes up.
    signal.signal(signal.SIGTERM, lambda *_: app.stop())
    if args.tray:
        from edash.host.tray import run_with_tray

        run_with_tray(app)
    else:
        try:
            app.run()
        except KeyboardInterrupt:
            app.stop()


def cmd_preview(args: argparse.Namespace) -> None:
    from edash.render.preview import render_preview

    config = load_config(_config_path(args, allow_example=True))
    now = datetime.fromisoformat(args.at).astimezone() if args.at else None
    paths, notes = render_preview(config, args.out, screen_ids=args.screen, now=now, scale=args.scale)
    for note in notes:
        print(f"warning: {note}", file=sys.stderr)
    for path in paths:
        print(path)


def cmd_edit(args: argparse.Namespace) -> None:
    import webbrowser

    from edash.host.editor.server import EditorServer

    save_path = args.config or _platform().default_config_path()
    load_path = save_path
    if not save_path.exists():
        print(f"No config at {save_path} yet, starting from the example. Saving creates it.")
        load_path = EXAMPLE_CONFIG
    server = EditorServer(load_path, save_path, args.port)
    print(f"Editor running at {server.url}\nPress Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def cmd_check(args: argparse.Namespace) -> None:
    from edash.render.screen import build_screens

    path = _config_path(args)
    _require_config(path)
    config = load_config(path)
    _, warnings = build_screens(config)
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"{path}: OK ({len(config.screens)} screens)")


def cmd_init_config(args: argparse.Namespace) -> None:
    path = args.config or _platform().default_config_path()
    if path.exists() and not args.force:
        sys.exit(f"{path} already exists (use --force to overwrite).")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXAMPLE_CONFIG, path)
    print(f"Wrote {path}")


def cmd_login(args: argparse.Namespace) -> None:
    import requests

    from edash.host.graph import GraphAuth, GraphError, NotLoggedIn

    platform = _platform()
    path = _config_path(args)
    _require_config(path)
    config = load_config(path)
    session = requests.Session()
    if config.host.proxy:
        session.proxies = {"http": config.host.proxy, "https": config.host.proxy}
    try:
        auth = GraphAuth(config.sources.graph, platform.token_cache_path(), platform, session)
        account = auth.login_device_code(print) if args.device_code else auth.login_interactive()
    except (NotLoggedIn, GraphError) as err:
        sys.exit(f"Login failed: {err}")
    print(f"Logged in as {account}.")


def cmd_ports(args: argparse.Namespace) -> None:
    ports = _platform().port_candidates()
    print("\n".join(ports) if ports else "No eDash device found.")


def cmd_ctl(args: argparse.Namespace) -> None:
    path = _config_path(args)
    port = load_config(path).host.control_port if path.exists() else 47811
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            sock.sendall(json.dumps({"action": args.action, "arg": args.arg}).encode() + b"\n")
            reply = json.loads(sock.makefile().readline())
    except OSError as err:
        sys.exit(f"Cannot reach a running edash-host on port {port}: {err}")
    print(json.dumps(reply, indent=2))
    if not reply.get("ok"):
        sys.exit(1)


def cmd_install_autostart(args: argparse.Namespace) -> None:
    path = _config_path(args)
    _require_config(path)
    for line in _platform().install_autostart(path.resolve()):
        print(line)


def cmd_uninstall_autostart(args: argparse.Namespace) -> None:
    for line in _platform().uninstall_autostart():
        print(line)


COMMANDS = {
    "run": cmd_run,
    "preview": cmd_preview,
    "edit": cmd_edit,
    "check": cmd_check,
    "init-config": cmd_init_config,
    "login": cmd_login,
    "ports": cmd_ports,
    "ctl": cmd_ctl,
    "install-autostart": cmd_install_autostart,
    "uninstall-autostart": cmd_uninstall_autostart,
}
