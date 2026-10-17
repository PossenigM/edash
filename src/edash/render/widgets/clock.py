from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field

from edash.render.context import RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_centered, fit_font
from edash.state import DashboardState
from edash.timeutil import next_minute


class ClockOptions(WidgetOptions):
    time_format: str = "%H:%M"
    date_format: str | None = "%A, %d %B"
    date_ratio: float = Field(0.28, ge=0.1, le=0.6)  # share of the height used by the date line


@widget("clock")
class Clock(Widget):
    Options = ClockOptions

    def render(self, ctx: RenderContext) -> None:
        o: ClockOptions = self.options
        box = ctx.box
        date_h = round(box.h * o.date_ratio) if o.date_format else 0
        time_box, date_box = box.split_top(box.h - date_h)

        text = ctx.now.strftime(o.time_format)
        # Size the font for all-zero digits so it does not change from minute to minute.
        sample = re.sub(r"\d", "0", text)
        font = fit_font(ctx.fonts, "bold", sample, time_box.w - 4, time_box.h - 4)
        draw_centered(ctx.draw, time_box, text, font, measure=sample)

        if o.date_format:
            date = ctx.now.strftime(o.date_format)
            date_font = fit_font(ctx.fonts, "regular", date, date_box.w - 4, date_box.h - 2, max_size=40)
            draw_centered(ctx.draw, date_box, date, date_font, measure="Ag")

    def next_update(self, state: DashboardState, now: datetime) -> datetime:
        return next_minute(now)
