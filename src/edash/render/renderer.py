from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from edash.config import DisplayConfig
from edash.render.context import BLACK, WHITE, RenderContext
from edash.render.fonts import Fonts
from edash.render.icons import draw_icon
from edash.render.layout import Box
from edash.render.screen import PlacedWidget, Screen
from edash.render.text import draw_line, line_height
from edash.state import DashboardState

log = logging.getLogger(__name__)

TITLE_SIZE = 18
FRAME_WIDTH = 2
FRAME_PADDING = 6

_TO_PANEL = {
    90: Image.Transpose.ROTATE_270,  # Pillow's rotations are counter-clockwise
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


@dataclass
class RenderResult:
    image: Image.Image  # logical orientation, mode "1"
    errors: list[str]


class Renderer:
    def __init__(self, display: DisplayConfig, fonts: Fonts | None = None):
        self.display = display
        self.fonts = fonts or Fonts()

    def render(self, screen: Screen, state: DashboardState, now: datetime) -> RenderResult:
        image = Image.new("1", self.display.logical_size, WHITE)
        errors: list[str] = []
        for placed in screen.widgets:
            image.paste(self._render_widget(placed, state, now, errors), placed.box.xy)
        return RenderResult(image, errors)

    def to_panel(self, image: Image.Image) -> Image.Image:
        transpose = _TO_PANEL.get(self.display.rotation)
        return image.transpose(transpose) if transpose is not None else image

    def next_update(self, screen: Screen, state: DashboardState, now: datetime) -> datetime | None:
        times = []
        for placed in screen.widgets:
            try:
                t = placed.widget.next_update(state, now)
            except Exception:
                log.exception("%s: next_update failed", placed.label)
                t = now + timedelta(minutes=1)
            if t is not None:
                times.append(t)
        return min(times, default=None)

    def _render_widget(
        self, placed: PlacedWidget, state: DashboardState, now: datetime, errors: list[str]
    ) -> Image.Image:
        tile = Image.new("1", (placed.box.w, placed.box.h), WHITE)
        draw = ImageDraw.Draw(tile)
        content = Box(0, 0, placed.box.w, placed.box.h)

        if placed.config.frame:
            draw.rectangle(content.rect, outline=BLACK, width=FRAME_WIDTH)
            content = content.inset(FRAME_WIDTH + FRAME_PADDING)
        if placed.config.title:
            font = self.fonts.get("bold", TITLE_SIZE)
            draw_line(draw, content.x, content.y, placed.config.title, font, content.w)
            rule_y = content.y + line_height(font) + 1
            draw.line((content.x, rule_y, content.right - 1, rule_y), fill=BLACK, width=2)
            _, content = content.split_top(rule_y - content.y + 6)
        if content.w <= 0 or content.h <= 0:
            return tile

        canvas = Image.new("1", (content.w, content.h), WHITE)
        ctx = RenderContext(canvas, ImageDraw.Draw(canvas), self.fonts, state, now)
        try:
            placed.widget.render(ctx)
        except Exception as err:
            log.exception("%s: render failed", placed.label)
            errors.append(f"{placed.label}: {err}")
            canvas = self._error_tile(content.w, content.h, f"{placed.config.type}: {err}")
        tile.paste(canvas, content.xy)
        return tile

    def _error_tile(self, w: int, h: int, message: str) -> Image.Image:
        canvas = Image.new("1", (w, h), WHITE)
        draw = ImageDraw.Draw(canvas)
        font = self.fonts.get("regular", 12)
        icon = min(h, 24)
        draw_icon(draw, "warning", Box(0, 0, icon, icon))
        draw_line(draw, icon + 4, max(0, (icon - line_height(font)) // 2), message, font, max(0, w - icon - 4))
        return canvas
