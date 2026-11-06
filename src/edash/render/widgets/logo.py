from __future__ import annotations

from typing import Literal

from edash.render.context import RenderContext
from edash.render.layout import Box
from edash.render.logo import logo_image
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_centered, fit_font, ink_bbox


class LogoOptions(WidgetOptions):
    text: str | None = None
    align: Literal["left", "center", "right"] = "center"


@widget("logo")
class Logo(Widget):
    """The eDash logo, optionally followed by a text such as "eDash" or a team name."""

    Options = LogoOptions

    def render(self, ctx: RenderContext) -> None:
        o: LogoOptions = self.options
        box = ctx.box
        size = min(box.w, box.h)
        gap = round(size * 0.25)
        text_w = 0
        if o.text:
            font = fit_font(ctx.fonts, "bold", o.text, max(1, box.w - size - gap), round(size * 0.62))
            left, _, right, _ = ink_bbox(font, o.text)
            text_w = right - left
        total = size + (gap + text_w if o.text else 0)
        x = {"left": 0, "center": (box.w - total) // 2, "right": box.w - total}[o.align]
        ctx.image.paste(logo_image(size), (x, (box.h - size) // 2))
        if o.text:
            draw_centered(ctx.draw, Box(x + size + gap, 0, text_w, box.h), o.text, font)
