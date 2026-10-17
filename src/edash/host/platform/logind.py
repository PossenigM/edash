"""Lock, sleep and shutdown events from systemd-logind over D-Bus (jeepney, pure Python).

Holds a "delay" inhibitor while running: on suspend/shutdown logind waits
until we release it (at most InhibitDelayMaxSec, 5 s by default), which gives
the display time to show the away screen before USB power goes.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from edash.host.platform.base import EventCallback

log = logging.getLogger(__name__)

LOGIN1 = "org.freedesktop.login1"
MANAGER = "org.freedesktop.login1.Manager"
SESSION = "org.freedesktop.login1.Session"
PROPERTIES = "org.freedesktop.DBus.Properties"

# How long to keep logind waiting after the away message went out: the device
# needs a full e-ink refresh (~4 s on the 7.5" V2). Stays below logind's 5 s cap.
HOLD_S = 4.0


def event_for(interface: str | None, member: str | None, body: tuple) -> str | None:
    """Map a logind signal to an event name, or None."""
    if interface == MANAGER and member == "PrepareForSleep" and body:
        return "suspend" if body[0] else "resume"
    if interface == MANAGER and member == "PrepareForShutdown" and body and body[0]:
        return "shutdown"
    if interface == SESSION and member == "Lock":
        return "lock"
    if interface == SESSION and member == "Unlock":
        return "unlock"
    if interface == PROPERTIES and member == "PropertiesChanged" and len(body) >= 2 and body[0] == SESSION:
        # Desktop lock screens (GNOME, KDE) report themselves via the LockedHint property.
        hint = body[1].get("LockedHint")
        if hint is not None:
            return "lock" if hint[1] else "unlock"
    return None


class LogindWatcher:
    def __init__(self, callback: EventCallback, hold_s: float = HOLD_S):
        self._callback = callback
        self._hold_s = hold_s
        self._inhibitor: Any = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="logind-events", daemon=True)

    def start(self) -> LogindWatcher:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    @property
    def inhibiting(self) -> bool:
        return self._inhibitor is not None

    def _run(self) -> None:
        try:
            from jeepney.bus_messages import MatchRule, message_bus
            from jeepney.io.blocking import open_dbus_connection
            from jeepney.low_level import HeaderFields, MessageType

            conn = open_dbus_connection(bus="SYSTEM", enable_fds=True)
        except Exception as err:
            log.warning("no system D-Bus (%s); lock/sleep events disabled", err)
            return

        rules = [
            MatchRule(type="signal", sender=LOGIN1, interface=MANAGER, member="PrepareForSleep"),
            MatchRule(type="signal", sender=LOGIN1, interface=MANAGER, member="PrepareForShutdown"),
            MatchRule(type="signal", sender=LOGIN1, interface=SESSION),
            MatchRule(type="signal", sender=LOGIN1, interface=PROPERTIES, member="PropertiesChanged", path_namespace="/org/freedesktop/login1/session"),
        ]
        with conn:
            for rule in rules:
                conn.send_and_get_reply(message_bus.AddMatch(rule))
            self._inhibit(conn)
            while not self._stop.is_set():
                try:
                    msg = conn.receive(timeout=1.0)
                except TimeoutError:
                    continue
                if msg.header.message_type != MessageType.signal:
                    continue
                fields = msg.header.fields
                event = event_for(fields.get(HeaderFields.interface), fields.get(HeaderFields.member), msg.body)
                if event:
                    self._dispatch(conn, event)
            self._release()

    def _dispatch(self, conn, event: str) -> None:
        try:
            self._callback(event)
        except Exception:
            log.exception("handling %s failed", event)
        if event in ("suspend", "shutdown"):
            time.sleep(self._hold_s)
            self._release()
        elif event == "resume":
            self._inhibit(conn)

    def _inhibit(self, conn) -> None:
        if self._inhibitor is not None:
            return
        from jeepney import DBusAddress, new_method_call

        manager = DBusAddress("/org/freedesktop/login1", bus_name=LOGIN1, interface=MANAGER)
        call = new_method_call(manager, "Inhibit", "ssss", ("sleep:shutdown", "eDash", "Show the away screen on the display", "delay"))
        try:
            reply = conn.send_and_get_reply(call, timeout=5)
            self._inhibitor = reply.body[0]
        except Exception as err:
            log.warning("cannot take a logind delay lock (%s); the away screen may not make it before suspend", err)

    def _release(self) -> None:
        if self._inhibitor is not None:
            self._inhibitor.close()
            self._inhibitor = None
