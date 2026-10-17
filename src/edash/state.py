from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from edash.protocol import CalendarData, DataMessage, Event, MailData, TeamsData, WeatherData


@dataclass(frozen=True)
class Away:
    reason: str | None  # "locked", "sleep", "shutdown", "stopped"
    since: datetime | None


@dataclass
class DashboardState:
    """Everything widgets render from. Lives in RAM on the device."""

    mail: MailData | None = None
    calendar: CalendarData | None = None
    teams: TeamsData | None = None
    weather: WeatherData | None = None
    fetched: dict[str, datetime] = field(default_factory=dict)
    fresh_until: dict[str, datetime] = field(default_factory=dict)
    host_connected: bool = False
    away: Away | None = None

    def apply(self, message: DataMessage, now: datetime) -> bool:
        """Store a data message; returns True if anything visible changed (data or staleness)."""
        topic = message.type
        was_stale = self.is_stale(topic, now)
        self.fetched[topic] = message.fetched_at or now
        if message.fresh_until is None:
            self.fresh_until.pop(topic, None)
        else:
            self.fresh_until[topic] = message.fresh_until
        changed = getattr(self, topic) != message.data
        if changed:
            setattr(self, topic, message.data)
        return changed or was_stale != self.is_stale(topic, now)

    def is_stale(self, topic: str, now: datetime) -> bool:
        until = self.fresh_until.get(topic)
        return until is not None and now >= until

    def timed_events(self) -> list[Event]:
        if self.calendar is None:
            return []
        return sorted((e for e in self.calendar.events if not e.all_day), key=lambda e: e.start)

    def current_event(self, now: datetime) -> Event | None:
        return next((e for e in self.timed_events() if e.start <= now < e.end), None)

    def next_event(self, now: datetime) -> Event | None:
        return next((e for e in self.timed_events() if e.start > now), None)
