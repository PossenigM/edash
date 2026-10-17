"""Hardware self-test: a test pattern, a series of partial refreshes, and a timing report.

Checks in one run whether the panel works at all, whether the orientation is
right, how fine detail and small text come out, how partial refresh looks
(flicker, ghosting) and how long refreshes take.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw

from edash.config import DisplayConfig
from edash.device.display import Display
from edash.render.context import BLACK, WHITE
from edash.render.fonts import Fonts
from edash.render.layout import Box
from edash.render.renderer import Renderer
from edash.render.text import draw_centered, draw_line, line_height

log = logging.getLogger(__name__)

STRIP_H = 72  # bottom strip used by the partial-refresh steps
CHECKER_CELLS = (1, 2, 4, 8)
FONT_SAMPLES = (("regular", 12), ("regular", 16), ("bold", 16), ("regular", 24), ("bold", 32))


@dataclass
class SelftestReport:
    full_s: list[float] = field(default_factory=list)
    partial_s: list[float] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.full_s:
            parts.append(f"full refresh {sum(self.full_s) / len(self.full_s):.2f} s")
        if self.partial_s:
            parts.append(
                f"partial refresh avg {sum(self.partial_s) / len(self.partial_s):.2f} s "
                f"(max {max(self.partial_s):.2f} s, {len(self.partial_s)}x)"
            )
        return " · ".join(parts)


def draw_pattern(size: tuple[int, int], fonts: Fonts, info: str) -> Image.Image:
    """Static test pattern on a logical (already rotated) canvas."""
    w, h = size
    image = Image.new("1", size, WHITE)
    draw = ImageDraw.Draw(image)

    # Edges: the outermost pixel row/column shows whether the panel crops anything.
    draw.rectangle((0, 0, w - 1, h - 1), outline=BLACK, width=1)
    draw.rectangle((4, 4, w - 5, h - 5), outline=BLACK, width=2)

    small = fonts.get("bold", 14)
    pad = 10
    draw_line(draw, pad, pad, "TOP LEFT", small, w // 3)
    draw_line(draw, w - pad - w // 3, pad, "TOP RIGHT", small, w // 3, align="right")
    corner_y = h - STRIP_H - line_height(small) - 6
    draw_line(draw, pad, corner_y, "BOTTOM LEFT", small, w // 3)
    draw_line(draw, w - pad - w // 3, corner_y, "BOTTOM RIGHT", small, w // 3, align="right")

    # "Up" arrow: if this does not point to the top of the frame, change display.rotation.
    cx = w // 2
    draw.polygon([(cx, pad), (cx - 14, pad + 20), (cx + 14, pad + 20)], fill=BLACK)
    draw_line(draw, cx - 40, pad + 22, "UP", small, 80, align="center")

    y = pad + 48
    title = fonts.get("bold", 30)
    draw_centered(draw, Box(0, y, w, line_height(title)), "eDash self-test", title)
    y += line_height(title) + 2
    regular = fonts.get("regular", 14)
    draw_line(draw, pad, y, info, regular, w - 2 * pad, align="center")
    y += line_height(regular) + 14

    # Checkerboards: 1 px detail is the hardest case for e-ink.
    cell_box = 56
    spacing = (w - 2 * pad - len(CHECKER_CELLS) * cell_box) // (len(CHECKER_CELLS) + 1)
    x = pad + spacing
    for cell in CHECKER_CELLS:
        for yy in range(cell_box):
            for xx in range(cell_box):
                if (xx // cell + yy // cell) % 2 == 0:
                    draw.point((x + xx, y + yy), fill=BLACK)
        draw.rectangle((x - 1, y - 1, x + cell_box, y + cell_box), outline=BLACK)
        draw_line(draw, x - 10, y + cell_box + 4, f"{cell} px", regular, cell_box + 20, align="center")
        x += cell_box + spacing
    y += cell_box + line_height(regular) + 14

    # Font samples, to judge legibility of small sizes without antialiasing.
    for role, size_pt in FONT_SAMPLES:
        font = fonts.get(role, size_pt)
        if y + line_height(font) > h - STRIP_H - line_height(small) - 10:
            break
        draw_line(draw, pad + 6, y, f"{role} {size_pt}: Meeting 09:30 – Äöü ß € 0123456789", font, w - 2 * pad - 12)
        y += line_height(font) + 2

    draw.line((4, h - STRIP_H, w - 5, h - STRIP_H), fill=BLACK, width=2)
    return image


def draw_partial_step(image: Image.Image, fonts: Fonts, step: int, steps: int) -> None:
    """Counter plus a square that moves across the strip: shows flicker, speed and ghosting."""
    w, h = image.size
    draw = ImageDraw.Draw(image)
    strip = Box(6, h - STRIP_H + 4, w - 12, STRIP_H - 10)
    draw.rectangle(strip.rect, fill=WHITE)
    font = fonts.get("bold", 22)
    label = f"Partial refresh {step}/{steps}"
    draw_line(draw, strip.x + 6, strip.y + (strip.h - line_height(font)) // 2, label, font, strip.w // 2)

    track = Box(strip.x + strip.w // 2, strip.y + 8, strip.w // 2 - 8, strip.h - 16)
    draw.rectangle(track.rect, outline=BLACK)
    square = track.h - 8
    x = track.x + 4 + round((track.w - square - 8) * (step - 1) / max(1, steps - 1))
    draw.rectangle((x, track.y + 4, x + square - 1, track.y + 4 + square - 1), fill=BLACK)


def draw_summary(image: Image.Image, fonts: Fonts, text: str) -> None:
    w, h = image.size
    draw = ImageDraw.Draw(image)
    strip = Box(6, h - STRIP_H + 4, w - 12, STRIP_H - 10)
    draw.rectangle(strip.rect, fill=WHITE)
    bold, regular = fonts.get("bold", 18), fonts.get("regular", 14)
    y = strip.y + (strip.h - line_height(bold) - line_height(regular)) // 2
    y += draw_line(draw, strip.x + 6, y, "Self-test done", bold, strip.w - 12)
    draw_line(draw, strip.x + 6, y, text or "no timings", regular, strip.w - 12)


def run_selftest(
    display: Display,
    *,
    rotation: int = 0,
    partial_steps: int = 10,
    pause: float = 1.0,
    fonts: Fonts | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    now: datetime | None = None,
) -> SelftestReport:
    fonts = fonts or Fonts()
    config = DisplayConfig(width=display.size[0], height=display.size[1], rotation=rotation)
    renderer = Renderer(config, fonts)
    report = SelftestReport()
    w, h = config.logical_size
    stamp = (now or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M")
    base = draw_pattern((w, h), fonts, f"{display.size[0]}×{display.size[1]} panel · rotation {rotation}° · {stamp}")

    def timed(refresh: Callable[[Image.Image], None], image: Image.Image, into: list[float]) -> None:
        start = clock()
        refresh(renderer.to_panel(image))
        into.append(clock() - start)

    log.info("full refresh with test pattern")
    timed(display.full, base, report.full_s)
    sleep(pause)

    for step in range(1, partial_steps + 1):
        frame = base.copy()
        draw_partial_step(frame, fonts, step, partial_steps)
        timed(display.partial, frame, report.partial_s)
        log.info("partial refresh %d/%d: %.2f s", step, partial_steps, report.partial_s[-1])
        sleep(pause)

    log.info("final full refresh")
    final = base.copy()
    draw_summary(final, fonts, report.summary())
    timed(display.full, final, report.full_s)
    display.sleep()
    return report
