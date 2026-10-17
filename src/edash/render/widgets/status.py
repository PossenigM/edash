from __future__ import annotations

from typing import Literal

from pydantic import Field

from edash.render.context import RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_line, line_height


class StatusOptions(WidgetOptions):
    font_size: int = Field(14, ge=8, le=32)
    align: Literal["left", "center", "right"] = "right"


@widget("status")
class Status(Widget):
    """Connection state and time of the last data update."""

    Options = StatusOptions

    def render(self, ctx: RenderContext) -> None:
        o: StatusOptions = self.options
        loc = ctx.locale
        parts = [loc.t("connected" if ctx.state.host_connected else "not_connected")]
        last = max(ctx.state.fetched.values(), default=None)
        if last is not None:
            parts.append(loc.t("updated", t=loc.when(last, ctx.now)))
        font = ctx.fonts.get("regular", o.font_size)
        y = (ctx.box.h - line_height(font)) // 2
        draw_line(ctx.draw, 0, y, " · ".join(parts), font, ctx.box.w, align=o.align)
