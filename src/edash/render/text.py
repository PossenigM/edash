"""Text measuring, truncating, wrapping and fitting for 1-bit rendering."""

from __future__ import annotations

import math

from PIL import ImageDraw

from edash.render.context import BLACK
from edash.render.fonts import Font, Fonts
from edash.render.layout import Box

ELLIPSIS = "…"


def text_width(font: Font, text: str) -> int:
    return math.ceil(font.getlength(text))


def line_height(font: Font) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def ellipsize(text: str, font: Font, max_width: int) -> str:
    if text_width(font, text) <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(font, text[:mid].rstrip() + ELLIPSIS) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return ELLIPSIS if text_width(font, ELLIPSIS) <= max_width else ""
    return text[:lo].rstrip() + ELLIPSIS


def wrap(text: str, font: Font, max_width: int, max_lines: int | None = None) -> list[str]:
    """Greedy word wrap; explicit newlines start new paragraphs. Overflow ends in an ellipsis."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if text_width(font, candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word if text_width(font, word) <= max_width else ellipsize(word, font, max_width)
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        rest = " ".join(lines[max_lines - 1 :])
        last = ellipsize(rest, font, max_width)
        if last == rest:  # the joined rest fits, but lines were dropped: still mark the cut
            last = ellipsize(rest + ELLIPSIS, font, max_width)
        lines = lines[: max_lines - 1] + [last]
    return lines


def ink_bbox(font: Font, text: str) -> tuple[int, int, int, int]:
    return font.getbbox(text)


def fit_font(
    fonts: Fonts, role: str, text: str, max_w: int, max_h: int, *, min_size: int = 8, max_size: int = 300
) -> Font:
    """Largest font size at which the ink of ``text`` fits into max_w x max_h."""
    best = fonts.get(role, min_size)
    lo, hi = min_size, max_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = fonts.get(role, mid)
        left, top, right, bottom = ink_bbox(font, text)
        if right - left <= max_w and bottom - top <= max_h:
            best, lo = font, mid + 1
        else:
            hi = mid - 1
    return best


def draw_centered(
    draw: ImageDraw.ImageDraw, box: Box, text: str, font: Font, fill: int = BLACK, *, measure: str | None = None
) -> None:
    """Center the ink of ``text`` in ``box``.

    ``measure`` is used for the vertical extent, so e.g. a clock does not jump
    up and down when its digits change.
    """
    left, top, right, bottom = ink_bbox(font, text)
    if measure is not None:
        _, top, _, bottom = ink_bbox(font, measure)
    x = box.x + (box.w - (right - left)) / 2 - left
    y = box.y + (box.h - (bottom - top)) / 2 - top
    draw.text((round(x), round(y)), text, font=font, fill=fill)


def draw_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: Font,
    max_width: int,
    fill: int = BLACK,
    align: str = "left",
) -> int:
    """Draw one ellipsized line with its ascender at ``y``; returns the line height."""
    text = ellipsize(text, font, max_width)
    if align == "right":
        x += max_width - text_width(font, text)
    elif align == "center":
        x += (max_width - text_width(font, text)) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return line_height(font)
