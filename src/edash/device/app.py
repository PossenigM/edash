from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import ValidationError

from edash.config import DeviceConfig
from edash.device.clock import Clock
from edash.device.display import Display
from edash.device.refresh import RefreshPolicy, RefreshTracker
from edash.device.screens import ScreenSelector
from edash.errors import ConfigError, format_validation_error
from edash.link import Connected, Connection, Disconnected, Invalid, LinkEvent, Received, Stream
from edash.protocol import (
    Ack,
    CalendarMsg,
    Command,
    ConfigMsg,
    Error,
    Hello,
    MailMsg,
    Message,
    Presence,
    Status,
    TeamsMsg,
    TimeSync,
    WeatherMsg,
)
from edash.render.renderer import Renderer
from edash.render.screen import build_screens
from edash.state import Away, DashboardState

log = logging.getLogger(__name__)

# The host syncs the time every 5 minutes by default; two missed syncs mean it is gone.
HOST_TIMEOUT_S = 11 * 60

# Shown until the host sends a config. No clock: the time is unknown before the first sync.
WAITING_CONFIG = DeviceConfig.model_validate(
    {
        "screens": [
            {
                "id": "waiting",
                "widgets": [
                    {"type": "text", "pos": [1, 2], "size": [10, 2], "options": {"text": "eDash", "bold": True}},
                    {
                        "type": "text",
                        "pos": [1, 4],
                        "size": [10, 1],
                        "options": {"text": "Waiting for the laptop…", "size": 24},
                    },
                ],
            }
        ]
    }
)


class DeviceApp:
    def __init__(self, display: Display, opener: Callable[[], Stream], clock: Clock | None = None):
        self.display = display
        self.clock = clock or Clock()
        self.state = DashboardState()
        self._inbox: queue.Queue[LinkEvent] = queue.Queue()
        self.connection = Connection(opener, self._inbox.put, name="host")
        self._stop = threading.Event()
        self._refresh = RefreshTracker()
        self._started = time.monotonic()
        self._last_rx: float | None = None
        self._dirty = True
        self._next_wake: datetime | None = None
        self._apply_config(WAITING_CONFIG)

    def run(self) -> None:
        self.connection.start()
        try:
            while not self._stop.is_set():
                self.step()
        finally:
            self.connection.stop()
            self.display.sleep()

    def stop(self) -> None:
        self._stop.set()
        self._inbox.put(Disconnected("stopping"))

    def step(self, max_wait: float = 60.0) -> None:
        """Redraw if needed, then wait for the next event or deadline."""
        now = self.clock.now()
        self._update_host_connected()
        screen_id = self.selector.select(self.state, now)
        due = self._next_wake is not None and now >= self._next_wake
        if self._dirty or due or screen_id != self._refresh.screen:
            self._redraw(screen_id, now)

        wait = max_wait
        if self._next_wake is not None:
            wait = min(wait, max(0.05, (self._next_wake - self.clock.now()).total_seconds()))
        try:
            event = self._inbox.get(timeout=wait)
        except queue.Empty:
            return
        self._handle(event)
        while True:
            try:
                self._handle(self._inbox.get_nowait())
            except queue.Empty:
                break

    def _apply_config(self, config: DeviceConfig) -> None:
        screens, warnings = build_screens(config)
        for warning in warnings:
            log.warning("config: %s", warning)
        self.config = config
        self.screens = screens
        self.renderer = Renderer(config.display)
        self.selector = ScreenSelector(config.rotation)
        self.policy = RefreshPolicy(config.display.full_refresh_every, config.display.max_partial_refreshes)
        self._dirty = True

    def _redraw(self, screen_id: str, now: datetime) -> None:
        screen = self.screens[screen_id]
        result = self.renderer.render(screen, self.state, now)
        panel = self.renderer.to_panel(result.image)
        decision = self._refresh.decide(self.policy, panel, screen_id, now)
        try:
            if decision == "full":
                self.display.full(panel)
            elif decision == "partial":
                self.display.partial(panel)
        except Exception:
            log.exception("display refresh failed")
            self._next_wake = now + timedelta(seconds=30)
            return
        self._refresh.record(decision, panel, screen_id, now)
        self._dirty = False
        self._next_wake = self.renderer.next_update(screen, self.state, now)
        log.debug("screen %s: %s refresh, next update %s", screen_id, decision, self._next_wake)

    def _update_host_connected(self) -> None:
        connected = self._last_rx is not None and time.monotonic() - self._last_rx < HOST_TIMEOUT_S
        if connected != self.state.host_connected:
            self.state.host_connected = connected
            self._dirty = True

    def _send(self, message) -> None:
        self.connection.send(message)

    def _handle(self, event: LinkEvent) -> None:
        match event:
            case Connected():
                log.info("serial port open")
                self._send(Hello(role="device"))
            case Disconnected(reason=reason):
                log.info("serial port closed: %s", reason)
            case Invalid(error=error):
                log.warning("%s", error)
                self._send(Error(message=error))
            case Received(message=message):
                self._last_rx = time.monotonic()
                self._handle_message(message)

    def _handle_message(self, msg: Message) -> None:
        now = self.clock.now()
        match msg:
            case Hello(role="host"):
                log.info("host connected (version %s, protocol %s)", msg.version, msg.protocol)
                self._send(Hello(role="device"))
            case TimeSync():
                first = not self.clock.synced
                self.clock.sync(msg.now)
                self._dirty |= first
            case ConfigMsg():
                try:
                    self._apply_config(DeviceConfig.model_validate(msg.config))
                except ValidationError as err:
                    self._send(Error(ref=msg.seq, message="; ".join(format_validation_error(err))))
                except ConfigError as err:
                    self._send(Error(ref=msg.seq, message="; ".join(err.messages)))
                else:
                    log.info("config applied (%d screens)", len(self.screens))
                    self._send(Ack(ref=msg.seq))
            case MailMsg() | CalendarMsg() | TeamsMsg() | WeatherMsg():
                if self.state.apply(msg, now):
                    self._dirty = True
            case Presence():
                away = Away(msg.reason, msg.since) if msg.away else None
                if away != self.state.away:
                    log.info("user %s", f"away ({msg.reason})" if away else "back")
                    self.state.away = away
                    self._dirty = True
            case Command(action="screen"):
                if msg.arg in (None, "auto"):
                    self.selector.override = None
                elif msg.arg in self.screens:
                    self.selector.override = msg.arg
                else:
                    self._send(Error(ref=msg.seq, message=f"unknown screen '{msg.arg}'"))
                    return
                self._dirty = True
                self._send(Ack(ref=msg.seq))
            case Command(action="refresh"):
                self._refresh.force_full = True
                self._dirty = True
                self._send(Ack(ref=msg.seq))
            case Command(action="status"):
                self._send(
                    Status(
                        screen=self._refresh.screen,
                        clock_synced=self.clock.synced,
                        partial_refreshes=self._refresh.partials,
                        last_full_refresh=self._refresh.last_full,
                        uptime_s=time.monotonic() - self._started,
                    )
                )
            case _:
                log.debug("ignoring %s", msg.type)
