from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from pydantic import field_validator

from edash.render.context import BLACK, WHITE, RenderContext
from edash.render.icons import ICONS, draw_icon
from edash.render.layout import Box
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_line, fit_font, line_height
from edash.state import DashboardState
from edash.timeutil import Duration, TimeRangeField, Weekdays


class ReminderOptions(WidgetOptions):
    label: str
    every: Duration
    active: TimeRangeField | None = None  # e.g. "08:00-17:00"; default: all day
    days: Weekdays = frozenset(range(5))  # default mon-fri
    highlight_for: Duration = timedelta(minutes=10)
    icon: str | None = None
    due_text: str | None = None

    @field_validator("every")
    @classmethod
    def _positive(cls, value: timedelta) -> timedelta:
        if value <= timedelta(0):
            raise ValueError("must be longer than 0")
        return value

    @field_validator("icon")
    @classmethod
    def _known_icon(cls, value: str | None) -> str | None:
        if value is not None and value not in ICONS:
            raise ValueError(f"unknown icon '{value}' (available: {', '.join(sorted(ICONS))})")
        return value


@dataclass(frozen=True)
class ReminderStatus:
    due: bool
    next_due: datetime | None
    next_change: datetime | None


def _windows(o: ReminderOptions, now: datetime) -> Iterator[tuple[datetime, datetime]]:
    """Active windows from yesterday on, in order. Without ``active`` a window is a whole day."""
    for offset in range(-1, 8):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in o.days:
            continue
        if o.active is None:
            start = datetime.combine(day, time(0), tzinfo=now.tzinfo)
            yield start, start + timedelta(days=1)
            continue
        start = datetime.combine(day, o.active.start, tzinfo=now.tzinfo)
        end = datetime.combine(day, o.active.end, tzinfo=now.tzinfo)
        yield start, end if end > start else end + timedelta(days=1)


def reminder_status(o: ReminderOptions, now: datetime) -> ReminderStatus:
    """Reminders fire every ``every`` after the window start and stay highlighted for ``highlight_for``.

    Stateless on purpose: the result only depends on the time, so a reboot or
    reconnect never shifts the schedule.
    """
    due_until = None
    next_due = None
    for start, end in _windows(o, now):
        if end <= now - o.highlight_for:
            continue
        if start <= now:
            k = math.floor((now - start) / o.every)
            last = start + k * o.every
            if k >= 1 and last < end and now < last + o.highlight_for:
                due_until = last + o.highlight_for
            candidate = start + (k + 1) * o.every
        else:
            candidate = start + o.every
        if now < candidate < end:
            next_due = candidate
            break
    changes = [t for t in (due_until, next_due) if t is not None]
    return ReminderStatus(due_until is not None, next_due, min(changes, default=None))


@widget("reminder")
class Reminder(Widget):
    Options = ReminderOptions

    def render(self, ctx: RenderContext) -> None:
        o: ReminderOptions = self.options
        status = reminder_status(o, ctx.now)
        draw, box = ctx.draw, ctx.box
        fg = WHITE if status.due else BLACK
        if status.due:
            draw.rounded_rectangle(box.rect, radius=8, fill=BLACK)

        inner = box.inset(6, 4)
        x = inner.x
        if o.icon:
            icon_s = min(inner.h, inner.w // 3)
            draw_icon(draw, o.icon, Box(inner.x, inner.y + (inner.h - icon_s) // 2, icon_s, icon_s), fill=fg, bg=BLACK if status.due else WHITE)
            x += icon_s + 8
        text_w = inner.right - x

        title = (o.due_text or f"{o.label}!") if status.due else o.label
        if status.due or status.next_due is None:
            sub = None
        elif status.next_due.date() == ctx.now.date():
            sub = f"next {status.next_due:%H:%M}"
        else:
            sub = f"next {status.next_due:%a %H:%M}"

        sub_font = ctx.fonts.get("regular", max(10, min(16, round(inner.h * 0.3))))
        sub_h = line_height(sub_font) if sub else 0
        title_font = fit_font(ctx.fonts, "bold", title, text_w, inner.h - sub_h, max_size=32)
        total = line_height(title_font) + sub_h
        y = inner.y + (inner.h - total) // 2
        y += draw_line(draw, x, y, title, title_font, text_w, fg)
        if sub:
            draw_line(draw, x, y, sub, sub_font, text_w, fg)

    def next_update(self, state: DashboardState, now: datetime) -> datetime | None:
        return reminder_status(self.options, now).next_change
