from __future__ import annotations

from datetime import datetime

from edash.config import RotationConfig
from edash.rules import parse_condition
from edash.state import DashboardState


class ScreenSelector:
    """Picks the screen: away screen while the user is away, else manual override, else rules
    (with a minimum dwell time), else the default."""

    def __init__(self, rotation: RotationConfig):
        self._default = rotation.default
        self._away = rotation.away_screen_id
        self._rules = [(parse_condition(r.when), r.screen) for r in rotation.rules]
        self._min_dwell = rotation.min_dwell
        self.current: str | None = None
        self._since: datetime | None = None
        self.override: str | None = None

    def wanted(self, state: DashboardState, now: datetime) -> str:
        for condition, screen in self._rules:
            if condition(state, now):
                return screen
        return self._default

    def select(self, state: DashboardState, now: datetime) -> str:
        if state.away is not None:
            return self._away
        if self.override:
            return self.override
        target = self.wanted(state, now)
        if self.current is None or (target != self.current and now - self._since >= self._min_dwell):
            self.current, self._since = target, now
        return self.current
