from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import Field

from edash.protocol import Event
from edash.render.context import BLACK, WHITE, RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_line, line_height, text_width
from edash.render.widgets._common import draw_placeholder
from edash.state import DashboardState
from edash.timeutil import start_of_day


class CalendarOptions(WidgetOptions):
    days: int = Field(1, ge=1, le=7)  # 1 = today only
    max_items: int = Field(10, ge=1, le=30)
    font_size: int = Field(16, ge=8, le=40)
    show_location: bool = True
    show_past: bool = False
    empty_text: str | None = None  # default: "No more meetings today" in the display language


@widget("calendar")
class Calendar(Widget):
    """Agenda list; the meeting in progress is drawn inverted."""

    Options = CalendarOptions
    topics = ("calendar",)

    def _events(self, state: DashboardState, now: datetime) -> list[Event]:
        if state.calendar is None:
            return []
        o: CalendarOptions = self.options
        horizon = start_of_day(now) + timedelta(days=o.days)
        events = [e for e in state.calendar.events if e.start < horizon and (o.show_past or e.end > now)]
        return sorted(events, key=lambda e: (e.start.astimezone(now.tzinfo).date(), not e.all_day, e.start))

    def render(self, ctx: RenderContext) -> None:
        o: CalendarOptions = self.options
        loc = ctx.locale
        if ctx.state.calendar is None:
            draw_placeholder(ctx, loc.t("waiting_calendar"))
            return
        events = self._events(ctx.state, ctx.now)
        if not events:
            empty = o.empty_text or loc.t("no_more_meetings" if o.days == 1 else "no_meetings")
            draw_placeholder(ctx, empty, size=o.font_size)
            return

        draw, box, now, tz = ctx.draw, ctx.box, ctx.now, ctx.now.tzinfo
        bold = ctx.fonts.get("bold", o.font_size)
        small = ctx.fonts.get("regular", max(8, o.font_size - 3))
        time_w = max(text_width(bold, "00:00"), text_width(small, loc.t("all_day"))) + 10
        text_w = box.w - time_w
        today = now.date()

        y, shown, current_day = 0, 0, None
        for ev in events[: o.max_items]:
            start, end = ev.start.astimezone(tz), ev.end.astimezone(tz)
            day = max(start.date(), today)
            if o.days > 1 and day != current_day:
                if day == today:
                    label = loc.t("today")
                elif day == today + timedelta(days=1):
                    label = loc.t("tomorrow")
                else:
                    label = loc.strftime(day, loc.t("day_header"))
                if y + line_height(small) + 4 > box.h:
                    break
                draw_line(draw, 0, y, label.upper(), small, box.w)
                y += line_height(small) + 4
                current_day = day

            details = [] if ev.all_day else [loc.t("until", t=f"{end:%H:%M}")]
            if o.show_location and ev.location:
                details.append(ev.location)
            elif ev.online:
                details.append(loc.t("online"))
            if ev.tentative:
                details.append(loc.t("tentative"))
            row_h = line_height(bold) + (line_height(small) if details else 0) + 6
            if y + row_h > box.h:
                break

            active = not ev.all_day and start <= now < end
            fg = WHITE if active else BLACK
            if active:
                draw.rectangle((0, y - 2, box.w - 1, y + row_h - 4), fill=BLACK)
            draw_line(
                draw,
                2,
                y,
                loc.t("all_day") if ev.all_day else f"{start:%H:%M}",
                small if ev.all_day else bold,
                time_w - 4,
                fg,
            )
            draw_line(draw, time_w, y, ev.subject, bold, text_w - 2, fg)
            if details:
                draw_line(draw, time_w, y + line_height(bold), " · ".join(details), small, text_w - 2, fg)
            y += row_h
            shown += 1

        hidden = len(events) - shown
        if hidden > 0 and y + line_height(small) <= box.h:
            draw_line(draw, time_w, y, loc.t("more", n=hidden), small, text_w)

    def next_update(self, state: DashboardState, now: datetime) -> datetime | None:
        boundaries = [t for e in self._events(state, now) for t in (e.start, e.end) if t > now]
        return min([*boundaries, start_of_day(now) + timedelta(days=1)])
