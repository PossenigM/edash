"""The eDash logo as a 1-bit image, drawn with the geometry of ``docs/images/logo.svg``."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from PIL import Image, ImageDraw

from edash.render.context import BLACK, WHITE

# The SVG uses a 64x64 grid. The tile left of this line is inverted.
_UNITS = 64
_SPLIT = [(0, 0), (40, 0), (24, 64), (0, 64)]
# Curves come out cleaner when drawn larger and thresholded after downscaling.
_SUPERSAMPLE = 4


@lru_cache(maxsize=16)
def logo_image(size: int) -> Image.Image:
    scale = size * _SUPERSAMPLE / _UNITS
    big = size * _SUPERSAMPLE

    def s(v: float) -> float:
        return v * scale

    light = Image.new("L", (big, big), WHITE)
    draw = ImageDraw.Draw(light)
    draw.rounded_rectangle((s(1), s(1), s(63), s(63)), radius=s(15), fill=BLACK)
    draw.rounded_rectangle((s(5), s(5), s(59), s(59)), radius=s(11), fill=WHITE)
    _letter(draw, s, BLACK)

    dark = Image.new("L", (big, big), WHITE)
    draw = ImageDraw.Draw(dark)
    draw.rounded_rectangle((s(1), s(1), s(63), s(63)), radius=s(15), fill=BLACK)
    _letter(draw, s, WHITE)

    mask = Image.new("L", (big, big), BLACK)
    ImageDraw.Draw(mask).polygon([(s(x), s(y)) for x, y in _SPLIT], fill=WHITE)
    combined = Image.composite(dark, light, mask)
    return combined.resize((size, size), Image.Resampling.LANCZOS).convert("1", dither=Image.Dither.NONE)


def _letter(draw: ImageDraw.ImageDraw, s: Callable[[float], float], fill: int) -> None:
    draw.rectangle((s(19), s(29.5), s(45), s(36.5)), fill=fill)
    draw.arc((s(15.5), s(16.5), s(48.5), s(49.5)), 40, 360, fill=fill, width=round(s(7)))
