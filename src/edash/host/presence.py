"""Turns OS events (lock, sleep, shutdown, ...) into presence messages for the device."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from edash.protocol import Presence

SystemEvent = Literal["lock", "unlock", "suspend", "resume", "shutdown", "stopped"]

# Event that starts an away reason, and the event that ends it.
_STARTS = {"lock": "locked", "suspend": "sleep", "shutdown": "shutdown", "stopped": "stopped"}
_ENDS = {"unlock": "locked", "resume": "sleep"}
# If several reasons are active (locked, then asleep), the first one here is shown.
_PRECEDENCE = ("shutdown", "sleep", "stopped", "locked")


class PresenceTracker:
    def __init__(self) -> None:
        self._active: dict[str, datetime] = {}  # reason -> since
        self._last: tuple[str, datetime] | None = None

    def handle(self, event: SystemEvent, now: datetime) -> Presence | None:
        """Apply an event; returns a message only if what the display should show changed."""
        if event in _STARTS:
            self._active.setdefault(_STARTS[event], now)
        elif event in _ENDS:
            self._active.pop(_ENDS[event], None)
        current = self._current()
        if current == self._last:
            return None
        self._last = current
        return self.message()

    def message(self) -> Presence:
        current = self._current()
        if current is None:
            return Presence(away=False)
        reason, since = current
        return Presence(away=True, reason=reason, since=since)

    @property
    def away(self) -> bool:
        return bool(self._active)

    def _current(self) -> tuple[str, datetime] | None:
        for reason in _PRECEDENCE:
            if reason in self._active:
                return reason, self._active[reason]
        return None
