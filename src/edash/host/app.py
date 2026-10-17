from __future__ import annotations

import json
import logging
import socketserver
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import serial

from edash.config import Config, load_config
from edash.errors import ConfigError
from edash.host.graph import NotLoggedIn
from edash.host.platform import Platform
from edash.host.presence import PresenceTracker, SystemEvent
from edash.host.sources import Source, build_sources
from edash.link import Connected, Connection, Disconnected, Invalid, LineLink, LinkEvent, ProtocolError, Received, Stream
from edash.protocol import Ack, Command, ConfigMsg, DataMessage, Error, Hello, Status, TimeSync

log = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 3.0
ERROR_RETRY_S = 120.0


def open_serial(port: str) -> serial.Serial:
    return serial.serial_for_url(port, baudrate=115200, timeout=1, write_timeout=5)


def probe(stream: Stream, timeout: float = PROBE_TIMEOUT_S) -> bool:
    """True if an eDash device answers a hello on this port (and not, e.g., the debug console)."""
    link = LineLink(stream)
    link.send(Hello(role="host"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = link.receive()
        except ProtocolError:
            continue
        if isinstance(message, Hello) and message.role == "device":
            return True
    return False


@dataclass
class _Scheduled:
    source: Source
    next_run: float = 0.0
    status: str = "pending"


@dataclass
class _Timers:
    time_sync: float = 0.0
    resend: float = 0.0


@dataclass
class HostStatus:
    device_connected: bool = False
    last_device_status: dict[str, Any] | None = None
    config_error: list[str] = field(default_factory=list)


class HostApp:
    def __init__(self, config_path: Path, platform: Platform):
        self.config_path = config_path
        self.platform = platform
        self.config: Config = load_config(config_path)
        self._config_mtime = config_path.stat().st_mtime
        self.status = HostStatus()
        self._latest: dict[str, DataMessage] = {}
        self._stop = threading.Event()
        self._reload_requested = threading.Event()
        self._presence = PresenceTracker()
        self._timers = _Timers()
        self._session = self._make_session()
        self._scheduled = self._schedule_sources()
        self.connection = Connection(self._open_device, self._on_event, name="device")

    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        server = _ControlServer(("127.0.0.1", self.config.host.control_port), self)
        threading.Thread(target=server.serve_forever, name="control", daemon=True).start()
        self.connection.start()
        watcher = None
        try:
            watcher = self.platform.start_event_watcher(self.on_system_event)
        except Exception:
            log.exception("lock/sleep events unavailable")
        log.info("eDash host running (config: %s)", self.config_path)
        try:
            while not self._stop.is_set():
                self._tick()
                self._stop.wait(1.0)
        finally:
            self.on_system_event("stopped")  # leave the away screen on the panel, not stale data
            if watcher:
                watcher.stop()
            server.shutdown()
            self.connection.stop()

    def stop(self) -> None:
        self._stop.set()

    def screen_ids(self) -> list[str]:
        return [s.id for s in self.config.screens]

    def on_system_event(self, event: SystemEvent) -> None:
        """Lock/sleep/shutdown events from the platform watcher (any thread)."""
        log.info("system event: %s", event)
        message = self._presence.handle(event, datetime.now().astimezone())
        if message is not None:
            self.connection.send(message)

    # --- main loop --------------------------------------------------------

    def _tick(self) -> None:
        force = self._reload_requested.is_set()
        self._reload_requested.clear()
        self._check_config_file(force=force)
        now_m = time.monotonic()
        for item in self._scheduled:
            if now_m >= item.next_run:
                self._run_source(item)
        if now_m >= self._timers.time_sync:
            self.connection.send(TimeSync(now=datetime.now().astimezone()))
            self._timers.time_sync = now_m + self.config.host.time_sync_every.total_seconds()
        if now_m >= self._timers.resend:
            for message in list(self._latest.values()):
                self.connection.send(message)
            self._timers.resend = now_m + self.config.host.resend_every.total_seconds()

    def _run_source(self, item: _Scheduled) -> None:
        source = item.source
        now = datetime.now().astimezone()
        try:
            message = source.fetch(now)
        except NotLoggedIn as err:
            self._set_status(item, f"not logged in: {err}", logging.WARNING)
            item.next_run = time.monotonic() + ERROR_RETRY_S
            return
        except Exception as err:
            self._set_status(item, f"error: {err}", logging.WARNING)
            item.next_run = time.monotonic() + min(ERROR_RETRY_S, source.interval.total_seconds())
            return
        message = message.model_copy(update={"fetched_at": now, "fresh_until": now + source.fresh_for})
        self._latest[source.topic] = message
        self.connection.send(message)
        self._set_status(item, "ok", logging.INFO)
        item.next_run = time.monotonic() + source.interval.total_seconds()

    def _set_status(self, item: _Scheduled, status: str, level: int) -> None:
        if status != item.status:  # log changes only, not every poll
            log.log(level, "%s: %s", item.source.topic, status)
        item.status = status

    # --- config -----------------------------------------------------------

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        if self.config.host.proxy:
            session.proxies = {"http": self.config.host.proxy, "https": self.config.host.proxy}
        return session

    def _schedule_sources(self) -> list[_Scheduled]:
        return [_Scheduled(s) for s in build_sources(self.config, self._session, self.platform)]

    def _check_config_file(self, force: bool = False) -> None:
        try:
            mtime = self.config_path.stat().st_mtime
        except OSError:
            return
        if mtime == self._config_mtime and not force:
            return
        self._config_mtime = mtime
        try:
            new = load_config(self.config_path)
        except ConfigError as err:
            self.status.config_error = err.messages
            log.error("%s\nKeeping the previous config.", err)
            return
        self.status.config_error = []
        old, self.config = self.config, new
        if new.sources != old.sources or new.host != old.host:
            self._session = self._make_session()
            self._scheduled = self._schedule_sources()
        self.connection.send(ConfigMsg(config=new.device_payload()))
        log.info("config reloaded")

    # --- device link ------------------------------------------------------

    def _open_device(self) -> Stream:
        port = self.config.host.port
        if port != "auto":
            return open_serial(port)
        candidates = self.platform.port_candidates()
        if not candidates:
            raise ConnectionError("no eDash device plugged in")
        for name in candidates:
            stream = open_serial(name)
            if probe(stream):
                log.info("found eDash on %s", name)
                return stream
            stream.close()
        raise ConnectionError(f"no eDash device answered on {', '.join(candidates)}")

    def _send_snapshot(self) -> None:
        self.connection.send(TimeSync(now=datetime.now().astimezone()))
        self.connection.send(ConfigMsg(config=self.config.device_payload()))
        self.connection.send(self._presence.message())
        for message in list(self._latest.values()):
            self.connection.send(message)

    def _on_event(self, event: LinkEvent) -> None:
        match event:
            case Connected():
                self.status.device_connected = True
                self._send_snapshot()
            case Disconnected(reason=reason):
                self.status.device_connected = False
                log.info("device disconnected: %s", reason)
            case Invalid(error=error):
                log.warning("from device: %s", error)
            case Received(message=Hello(role="device") as hello):
                log.info("device says hello (version %s)", hello.version)
                self._send_snapshot()
            case Received(message=Error() as error):
                log.error("device rejected message %s: %s", error.ref, error.message)
            case Received(message=Status() as status):
                self.status.last_device_status = status.model_dump(mode="json")
            case Received(message=Ack()):
                pass

    # --- control (CLI `edash-host ctl`, tray) -----------------------------

    def control(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "screen":
            sent = self.connection.send(Command(action="screen", arg=request.get("arg") or "auto"))
            return {"ok": sent}
        if action == "refresh":
            return {"ok": self.connection.send(Command(action="refresh"))}
        if action == "fetch":
            for item in self._scheduled:
                item.next_run = 0.0
            return {"ok": True}
        if action == "reload":
            self._reload_requested.set()  # handled by the main loop, which owns config and sources
            return {"ok": True}
        if action == "status":
            self.connection.send(Command(action="status"))
            return {
                "ok": True,
                "config": str(self.config_path),
                "device_connected": self.status.device_connected,
                "presence": self._presence.message().model_dump(mode="json", exclude={"seq", "type"}),
                "device": self.status.last_device_status,
                "sources": {item.source.topic: item.status for item in self._scheduled},
                "config_errors": self.status.config_error,
            }
        return {"ok": False, "error": f"unknown action {action!r}"}


class _ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            request = json.loads(self.rfile.readline(65536))
            reply = self.server.app.control(request)  # type: ignore[attr-defined]
        except Exception as err:
            reply = {"ok": False, "error": str(err)}
        self.wfile.write(json.dumps(reply).encode() + b"\n")


class _ControlServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: HostApp):
        super().__init__(address, _ControlHandler)
        self.app = app
