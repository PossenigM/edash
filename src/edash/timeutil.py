"""Durations, time-of-day ranges and weekday sets used in config, rules and widgets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Annotated, Any

from pydantic import PlainSerializer, PlainValidator

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_DURATION_RE = re.compile(r"^(?:\d+(?:\.\d+)?[dhms])+$")
_PART_RE = re.compile(r"(\d+(?:\.\d+)?)([dhms])")

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_duration(value: Any) -> timedelta:
    """Parse ``90s``, ``45m``, ``1h30m``, ``2d`` or a plain number of seconds."""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return timedelta(seconds=value)
    if isinstance(value, str):
        text = value.replace(" ", "").lower()
        if _DURATION_RE.match(text):
            return timedelta(seconds=sum(float(n) * _UNITS[u] for n, u in _PART_RE.findall(text)))
    raise ValueError(f"invalid duration {value!r}, expected e.g. '30s', '45m' or '1h30m'")


def _parse_time(text: str) -> time:
    try:
        hour, minute = text.strip().split(":")
        return time(int(hour), int(minute))
    except ValueError:
        raise ValueError(f"invalid time {text!r}, expected HH:MM") from None


@dataclass(frozen=True)
class TimeRange:
    """A daily time window like ``08:00-17:00``; may wrap past midnight (``22:00-06:00``)."""

    start: time
    end: time

    @classmethod
    def parse(cls, value: Any) -> TimeRange:
        if isinstance(value, TimeRange):
            return value
        if not isinstance(value, str) or value.count("-") != 1:
            raise ValueError(f"invalid time range {value!r}, expected e.g. '08:00-17:00'")
        start, end = value.split("-")
        return cls(_parse_time(start), _parse_time(end))

    def __contains__(self, t: time) -> bool:
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end

    def __str__(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"


def parse_weekdays(value: Any) -> frozenset[int]:
    """Parse ``mon-fri``, ``sat,sun`` or a list of day names into weekday numbers (Mon=0)."""
    if isinstance(value, (set, frozenset)) and all(isinstance(d, int) for d in value):
        return frozenset(value)
    parts = value.split(",") if isinstance(value, str) else list(value)
    days: set[int] = set()
    for part in parts:
        part = str(part).strip().lower()
        first, _, last = part.partition("-")
        if first not in WEEKDAYS or (last and last not in WEEKDAYS):
            raise ValueError(f"invalid weekday {part!r}, use {', '.join(WEEKDAYS)} or ranges like mon-fri")
        a = WEEKDAYS.index(first)
        b = WEEKDAYS.index(last) if last else a
        days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])
    return frozenset(days)


Duration = Annotated[
    timedelta,
    PlainValidator(parse_duration),
    PlainSerializer(lambda td: td.total_seconds(), return_type=float),
]
TimeRangeField = Annotated[
    TimeRange,
    PlainValidator(TimeRange.parse),
    PlainSerializer(str, return_type=str),
]
Weekdays = Annotated[
    frozenset[int],
    PlainValidator(parse_weekdays),
    PlainSerializer(lambda days: [WEEKDAYS[d] for d in sorted(days)], return_type=list),
]


def next_minute(now: datetime) -> datetime:
    return (now + timedelta(minutes=1)).replace(second=0, microsecond=0)


def start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
