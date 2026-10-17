from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from edash.protocol import CalendarData, DataMessage, Event, MailData, TeamsData, WeatherData


@dataclass
class DashboardState:
    """Everything widgets render from. Lives in RAM on the device."""

    mail: MailData | None = None
    calendar: CalendarData | None = None
    teams: TeamsData | None = None
    weather: WeatherData | None = None
    updated: dict[str, datetime] = field(default_factory=dict)
    host_connected: bool = False

    def apply(self, message: DataMessage, now: datetime) -> bool:
        """Store a data message; returns True if the content changed."""
        topic = message.type
        self.updated[topic] = now
        if getattr(self, topic) == message.data:
            return False
        setattr(self, topic, message.data)
        return True

    def timed_events(self) -> list[Event]:
        if self.calendar is None:
            return []
        return sorted((e for e in self.calendar.events if not e.all_day), key=lambda e: e.start)

    def current_event(self, now: datetime) -> Event | None:
        return next((e for e in self.timed_events() if e.start <= now < e.end), None)

    def next_event(self, now: datetime) -> Event | None:
        return next((e for e in self.timed_events() if e.start > now), None)
