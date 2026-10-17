from __future__ import annotations

from typing import Literal

from pydantic import Field

from edash.render.context import BLACK, WHITE, RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_line, line_height, wrap


class TextOptions(WidgetOptions):
    text: str
    size: int | None = Field(None, ge=6, le=300)  # None = as large as fits
    bold: bool = False
    align: Literal["left", "center", "right"] = "center"
    invert: bool = False


@widget("text")
class Text(Widget):
    """Static text, e.g. a note, a name plate or a 'do not disturb' sign."""

    Options = TextOptions

    def render(self, ctx: RenderContext) -> None:
        o: TextOptions = self.options
        draw, box = ctx.draw, ctx.box
        role = "bold" if o.bold else "regular"
        fg = WHITE if o.invert else BLACK
        if o.invert:
            draw.rectangle(box.rect, fill=BLACK)

        if o.size is not None:
            font = ctx.fonts.get(role, o.size)
            lines = wrap(o.text, font, box.w, max_lines=max(1, box.h // line_height(font)))
        else:
            font = ctx.fonts.get(role, 8)
            lines = wrap(o.text, font, box.w, max_lines=1)
            for size in range(min(box.h, 160), 7, -2):
                font = ctx.fonts.get(role, size)
                lines = wrap(o.text, font, box.w)
                if len(lines) * line_height(font) <= box.h:
                    break

        y = (box.h - len(lines) * line_height(font)) // 2
        for line in lines:
            y += draw_line(draw, 0, y, line, font, box.w, fg, align=o.align)
