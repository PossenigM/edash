from __future__ import annotations

import math
from datetime import datetime, timedelta

from edash.protocol import Event
from edash.render.context import BLACK, RenderContext
from edash.render.layout import Box
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_line, fit_font, line_height, wrap
from edash.render.widgets._common import draw_placeholder
from edash.state import DashboardState
from edash.timeutil import Duration, next_minute


class NextMeetingOptions(WidgetOptions):
    lookahead: Duration = timedelta(hours=12)
    empty_text: str | None = None  # default: "No upcoming meetings" in the display language


@widget("next_meeting")
class NextMeeting(Widget):
    """The running meeting, or the next one with a countdown."""

    Options = NextMeetingOptions
    topics = ("calendar",)

    def _pick(self, state: DashboardState, now: datetime) -> tuple[Event | None, bool]:
        current = state.current_event(now)
        if current:
            return current, True
        upcoming = state.next_event(now)
        if upcoming and upcoming.start - now <= self.options.lookahead:
            return upcoming, False
        return None, False

    def render(self, ctx: RenderContext) -> None:
        loc = ctx.locale
        if ctx.state.calendar is None:
            draw_placeholder(ctx, loc.t("waiting_calendar"))
            return
        event, running = self._pick(ctx.state, ctx.now)
        if event is None:
            draw_placeholder(ctx, self.options.empty_text or loc.t("no_upcoming"), size=24)
            return

        draw, box, now = ctx.draw, ctx.box, ctx.now
        start, end = event.start.astimezone(now.tzinfo), event.end.astimezone(now.tzinfo)
        if running:
            label = loc.t("now_until", t=f"{end:%H:%M}")
        else:
            minutes = math.ceil((start - now).total_seconds() / 60)
            if minutes < 60:
                label = loc.t("in_minutes", n=minutes)
            elif start.date() == now.date():
                label = loc.t("at", t=f"{start:%H:%M}")
            else:
                label = loc.strftime(start, "%a %H:%M").upper()

        label_font = fit_font(ctx.fonts, "bold", label, box.w, round(box.h * 0.16), max_size=48)
        y = draw_line(draw, 0, 0, label, label_font, box.w) + 4
        draw.line((0, y, box.w - 1, y), fill=BLACK, width=3)
        y += 10

        details = [f"{start:%H:%M}–{end:%H:%M}"]
        if event.location:
            details.append(event.location)
        elif event.online:
            details.append(loc.t("online_meeting"))
        detail_font = ctx.fonts.get("regular", max(12, min(28, round(box.h * 0.08))))
        detail_h = line_height(detail_font)
        subject_box = Box(0, y, box.w, box.h - y - detail_h - 6)

        # Largest subject font that fits in at most three lines.
        font = ctx.fonts.get("bold", 12)
        lines = wrap(event.subject, font, subject_box.w, max_lines=1)
        for size in range(min(72, subject_box.h), 11, -2):
            font = ctx.fonts.get("bold", size)
            lines = wrap(event.subject, font, subject_box.w, max_lines=3)
            if len(lines) * line_height(font) <= subject_box.h:
                break
        for line in lines:
            y += draw_line(draw, 0, y, line, font, box.w)
        draw_line(draw, 0, box.h - detail_h, " · ".join(details), detail_font, box.w)

    def next_update(self, state: DashboardState, now: datetime) -> datetime | None:
        event, _ = self._pick(state, now)
        if event is not None:
            return next_minute(now)
        upcoming = state.next_event(now)
        return upcoming.start - self.options.lookahead if upcoming else None
