from __future__ import annotations

from datetime import datetime

from edash.render.context import RenderContext
from edash.render.icons import draw_icon
from edash.render.layout import Box
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_centered, draw_line, fit_font, line_height, wrap

REASONS = {
    "locked": ("lock", "Laptop locked since {t}"),
    "sleep": ("moon", "Laptop asleep since {t}"),
    "shutdown": ("power", "Laptop shut down at {t}"),
    "stopped": ("power", "eDash host stopped at {t}"),
}
TITLE_GAP = 28
LINE_GAP = 10


class AwayOptions(WidgetOptions):
    title: str = "Away"
    message: str | None = None  # e.g. "Back at 14:00" or "Ask Alex for keys"
    show_next_meeting: bool = True


def _when(dt: datetime, now: datetime) -> str:
    local = dt.astimezone(now.tzinfo)
    return f"{local:%H:%M}" if local.date() == now.date() else f"{local:%a %H:%M}"


@widget("away")
class AwayWidget(Widget):
    """Shown while the laptop is locked, asleep or off. Deliberately has no clock:
    the Pi may lose power with the laptop, and a frozen time would be wrong."""

    Options = AwayOptions
    topics = ("calendar",)

    def render(self, ctx: RenderContext) -> None:
        o: AwayOptions = self.options
        draw, box, now = ctx.draw, ctx.box, ctx.now
        away = ctx.state.away
        icon, template = REASONS.get(away.reason if away else None, (None, None))

        texts: list[tuple[str, int, str]] = []  # text, size, role
        if template and away.since:
            texts.append((template.format(t=_when(away.since, now)), 26, "regular"))
        if o.message:
            texts.append((o.message, 26, "bold"))
        if o.show_next_meeting:
            event = ctx.state.next_event(now)
            if event:
                texts.append((f"Next: {event.subject} · {_when(event.start, now)}", 20, "regular"))

        text_w = box.w - 40
        blocks = []  # (lines, font)
        for text, size, role in texts:
            font = ctx.fonts.get(role, size)
            blocks.append((wrap(text, font, text_w, max_lines=2), font))
        text_h = sum(len(lines) * line_height(font) + LINE_GAP for lines, font in blocks)

        # Title (with icon) gets what the text leaves, up to a third of the height.
        title_h = max(20, min(round(box.h * 0.32), box.h - text_h - TITLE_GAP))
        title_font = fit_font(ctx.fonts, "bold", o.title, round(box.w * 0.7), title_h, max_size=140)
        left, _, right, _ = title_font.getbbox(o.title)
        title_w = right - left
        icon_s = round(title_h * 0.8) if icon else 0
        gap = 24 if icon else 0

        y = max(0, (box.h - title_h - TITLE_GAP - text_h) // 2)
        x = (box.w - title_w - icon_s - gap) // 2
        if icon:
            draw_icon(draw, icon, Box(x, y + (title_h - icon_s) // 2, icon_s, icon_s))
        draw_centered(draw, Box(x + icon_s + gap, y, title_w, title_h), o.title, title_font)
        y += title_h + TITLE_GAP

        for lines, font in blocks:
            for line in lines:
                if y + line_height(font) > box.h:
                    return
                y += draw_line(draw, 20, y, line, font, text_w, align="center")
            y += LINE_GAP
