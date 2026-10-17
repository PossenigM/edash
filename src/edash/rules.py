"""A tiny, safe condition language for screen rotation rules.

Clauses, optionally combined with ``and`` and negated with ``not``::

    meeting_active
    meeting_starts_in <= 5m
    unread_mail > 0
    unread_teams >= 3
    host_connected
    time in 18:30-07:00
    weekday in sat,sun
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from edash.state import DashboardState
from edash.timeutil import TimeRange, parse_duration, parse_weekdays

Check = Callable[[DashboardState, datetime], bool]

_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}
_CMP_RE = re.compile(r"^(\w+)\s*(<=|>=|==|!=|<|>)\s*(\S+)$")
_IN_RE = re.compile(r"^(\w+)\s+in\s+(.+)$")


def _meeting_starts_in(state: DashboardState, now: datetime) -> timedelta | None:
    event = state.next_event(now)
    return event.start - now if event else None


_FLAGS: dict[str, Check] = {
    "meeting_active": lambda s, now: s.current_event(now) is not None,
    "host_connected": lambda s, now: s.host_connected,
}
_DURATIONS: dict[str, Callable[[DashboardState, datetime], timedelta | None]] = {
    "meeting_starts_in": _meeting_starts_in,
}
_COUNTS: dict[str, Callable[[DashboardState, datetime], int]] = {
    "unread_mail": lambda s, now: s.mail.unread_count if s.mail else 0,
    "unread_teams": lambda s, now: s.teams.unread_count if s.teams else 0,
}
_KNOWN = ", ".join([*_FLAGS, *_DURATIONS, *_COUNTS, "time in …", "weekday in …"])


@dataclass(frozen=True)
class Condition:
    text: str
    checks: tuple[Check, ...]

    def __call__(self, state: DashboardState, now: datetime) -> bool:
        return all(check(state, now) for check in self.checks)


def parse_condition(text: str) -> Condition:
    clauses = [c.strip() for c in re.split(r"\s+and\s+", text.strip())]
    if not text.strip() or not all(clauses):
        raise ValueError("empty condition")
    return Condition(text, tuple(_parse_clause(c) for c in clauses))


def _parse_clause(clause: str) -> Check:
    if clause.startswith("not "):
        inner = _parse_positive(clause[4:].strip())
        return lambda s, now: not inner(s, now)
    return _parse_positive(clause)


def _parse_positive(clause: str) -> Check:
    if clause in _FLAGS:
        return _FLAGS[clause]

    if m := _IN_RE.match(clause):
        name, value = m.groups()
        if name == "time":
            window = TimeRange.parse(value.strip())
            return lambda s, now: now.time() in window
        if name == "weekday":
            days = parse_weekdays(value)
            return lambda s, now: now.weekday() in days
        raise ValueError(f"'{name} in …' is not supported, only 'time in' and 'weekday in'")

    if m := _CMP_RE.match(clause):
        name, op, raw = m.groups()
        compare = _OPS[op]
        if name in _DURATIONS:
            limit = parse_duration(raw)
            get_duration = _DURATIONS[name]

            def check_duration(s: DashboardState, now: datetime) -> bool:
                value = get_duration(s, now)
                return value is not None and compare(value, limit)

            return check_duration
        if name in _COUNTS:
            try:
                count = int(raw)
            except ValueError:
                raise ValueError(f"'{name}' needs a whole number, got {raw!r}") from None
            get_count = _COUNTS[name]
            return lambda s, now: compare(get_count(s, now), count)
        raise ValueError(f"unknown variable '{name}' (known: {_KNOWN})")

    raise ValueError(f"cannot parse condition '{clause}' (known: {_KNOWN})")
