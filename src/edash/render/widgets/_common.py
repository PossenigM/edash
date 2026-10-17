from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edash.render.context import BLACK, RenderContext
from edash.render.i18n import Locale
from edash.render.icons import draw_icon
from edash.render.layout import Box
from edash.render.text import draw_line, line_height, text_width, wrap


def draw_placeholder(ctx: RenderContext, text: str, box: Box | None = None, size: int = 16) -> None:
    box = box or ctx.box
    font = ctx.fonts.get("regular", size)
    lines = wrap(text, font, box.w, max_lines=max(1, box.h // line_height(font)))
    y = box.y + (box.h - len(lines) * line_height(font)) // 2
    for line in lines:
        y += draw_line(ctx.draw, box.x, y, line, font, box.w, align="center")


def short_time(dt: datetime, now: datetime, locale: Locale) -> str:
    """``14:05`` today, ``yesterday``, otherwise a short date like ``12 Oct`` / ``12.10.``."""
    local = dt.astimezone(now.tzinfo)
    days_ago = (now.date() - local.date()).days
    if days_ago == 0:
        return f"{local:%H:%M}"
    if days_ago == 1:
        return locale.t("yesterday")
    return locale.strftime(local, locale.t("date_short"))


@dataclass
class Row:
    title: str
    body: str
    time: str
    prefix: str = ""


def draw_message_list(
    ctx: RenderContext,
    *,
    icon: str,
    header: str,
    rows: list[Row],
    max_items: int,
    font_size: int,
    show_header: bool,
    empty_text: str,
) -> None:
    """Shared layout of the mail and Teams widgets: header, then two-line rows."""
    draw, box = ctx.draw, ctx.box
    y = 0
    if show_header:
        header_font = ctx.fonts.get("bold", font_size + 4)
        hh = line_height(header_font)
        draw_icon(draw, icon, Box(0, 0, hh, hh))
        draw_line(draw, hh + 8, 0, header, header_font, box.w - hh - 8)
        y = hh + 6

    if not rows:
        draw_placeholder(ctx, empty_text, Box(0, y, box.w, box.h - y), size=font_size)
        return

    bold = ctx.fonts.get("bold", font_size)
    regular = ctx.fonts.get("regular", font_size)
    small = ctx.fonts.get("regular", max(8, font_size - 2))
    row_h = line_height(bold) + line_height(regular) + 6
    more_h = line_height(small)

    shown = 0
    for row in rows[:max_items]:
        remaining = len(rows) - shown - 1
        needed = row_h + (more_h if remaining else 0)
        if y + needed > box.h:
            break
        time_w = text_width(small, row.time)
        draw_line(draw, 0, y, row.prefix + row.title, bold, box.w - time_w - 8)
        draw_line(draw, box.w - time_w, y + 2, row.time, small, time_w)
        draw_line(draw, 0, y + line_height(bold), row.body, regular, box.w)
        y += row_h
        shown += 1
        if shown < min(len(rows), max_items):
            for x in range(0, box.w, 3):
                draw.point((x, y - 4), fill=BLACK)

    hidden = len(rows) - shown
    if hidden > 0 and y + more_h <= box.h:
        draw_line(draw, 0, y, ctx.locale.t("more", n=hidden), small, box.w)
