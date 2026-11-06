from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from edash.config import DisplayConfig
from edash.render.context import BLACK, WHITE, RenderContext
from edash.render.fonts import Fonts
from edash.render.i18n import get_locale
from edash.render.icons import draw_icon
from edash.render.layout import Box
from edash.render.screen import PlacedWidget, Screen
from edash.render.text import draw_line, line_height, text_width
from edash.state import DashboardState

log = logging.getLogger(__name__)

TITLE_SIZE = 18
STALE_SIZE = 12
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
        self.locale = get_locale(display.language)

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
            if placed.config.show_stale:  # redraw when data turns stale, to add the marker
                times.extend(u for topic in placed.widget.topics if (u := state.fresh_until.get(topic)) and u > now)
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
        title_box = None
        if placed.config.title:
            font = self.fonts.get("bold", TITLE_SIZE)
            draw_line(draw, content.x, content.y, placed.config.title, font, content.w)
            title_box = Box(content.x, content.y, content.w, line_height(font))
            rule_y = content.y + line_height(font) + 1
            draw.line((content.x, rule_y, content.right - 1, rule_y), fill=BLACK, width=2)
            _, content = content.split_top(rule_y - content.y + 6)
        if content.w <= 0 or content.h <= 0:
            return tile

        canvas = Image.new("1", (content.w, content.h), WHITE)
        ctx = RenderContext(canvas, ImageDraw.Draw(canvas), self.fonts, state, now, self.locale)
        try:
            placed.widget.render(ctx)
        except Exception as err:
            log.exception("%s: render failed", placed.label)
            errors.append(f"{placed.label}: {err}")
            canvas = self._error_tile(content.w, content.h, f"{placed.config.type}: {err}")
        tile.paste(canvas, content.xy)

        if placed.config.show_stale:
            stale = [t for t in placed.widget.topics if state.is_stale(t, now) and t in state.fetched]
            if stale:
                as_of = min(state.fetched[t] for t in stale)
                self._draw_stale_marker(draw, title_box or content, as_of, now, in_title=title_box is not None)
        return tile

    def _draw_stale_marker(
        self, draw: ImageDraw.ImageDraw, area: Box, as_of: datetime, now: datetime, in_title: bool
    ) -> None:
        """Inverted "as of 09:12" label: right end of the title bar, or the top-right corner
        (where list widgets have their header and the weather widget has free space)."""
        text = self.locale.t("as_of", t=self.locale.when(as_of, now))
        font = self.fonts.get("bold", STALE_SIZE)
        w = text_width(font, text) + 8
        h = line_height(font) + 2
        x = area.right - w
        y = area.y + (area.h - h) // 2 if in_title else area.y
        draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=3, fill=BLACK)
        draw.text((x + 4, y + 1), text, font=font, fill=WHITE)

    def _error_tile(self, w: int, h: int, message: str) -> Image.Image:
        canvas = Image.new("1", (w, h), WHITE)
        draw = ImageDraw.Draw(canvas)
        font = self.fonts.get("regular", 12)
        icon = min(h, 24)
        draw_icon(draw, "warning", Box(0, 0, icon, icon))
        draw_line(draw, icon + 4, max(0, (icon - line_height(font)) // 2), message, font, max(0, w - icon - 4))
        return canvas
