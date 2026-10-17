"""Vector icons drawn with Pillow primitives, so they stay crisp at any size in 1-bit."""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import ImageDraw

from edash.render.context import BLACK, WHITE
from edash.render.layout import Box

IconFn = Callable[[ImageDraw.ImageDraw, "_Pen"], None]


class _Pen:
    """Maps fractional coordinates (0..1) of a square icon box to pixels."""

    def __init__(self, x: int, y: int, size: int, fill: int, bg: int):
        self.x, self.y, self.s = x, y, size
        self.fill, self.bg = fill, bg
        self.lw = max(1, round(size / 14))

    def p(self, fx: float, fy: float) -> tuple[float, float]:
        return self.x + fx * self.s, self.y + fy * self.s

    def rect(self, fx0: float, fy0: float, fx1: float, fy1: float) -> tuple[float, float, float, float]:
        return (*self.p(fx0, fy0), *self.p(fx1, fy1))


def _cloud(draw: ImageDraw.ImageDraw, pen: _Pen, fx: float, fy: float, fw: float, fh: float) -> None:
    """Outlined cloud in the given fractional region: filled shapes, then interiors erased."""
    shapes = [
        ("ellipse", (0.00, 0.40, 0.45, 1.00)),
        ("ellipse", (0.22, 0.00, 0.78, 0.92)),
        ("ellipse", (0.55, 0.30, 1.00, 1.00)),
        ("rect", (0.22, 0.60, 0.78, 1.00)),
    ]

    def region(f: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        return pen.rect(fx + f[0] * fw, fy + f[1] * fh, fx + f[2] * fw, fy + f[3] * fh)

    for colour, shrink in ((pen.fill, 0), (pen.bg, pen.lw)):
        for kind, f in shapes:
            x0, y0, x1, y1 = region(f)
            box = (x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink)
            if kind == "ellipse":
                draw.ellipse(box, fill=colour)
            else:
                draw.rectangle(box, fill=colour)


def _sun_at(draw: ImageDraw.ImageDraw, pen: _Pen, fcx: float, fcy: float, fr: float) -> None:
    cx, cy = pen.p(fcx, fcy)
    r = fr * pen.s
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=pen.fill, width=pen.lw)
    for i in range(8):
        a = i * math.pi / 4
        draw.line(
            (cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45, cx + math.cos(a) * r * 1.95, cy + math.sin(a) * r * 1.95),
            fill=pen.fill,
            width=pen.lw,
        )


def sun(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _sun_at(draw, pen, 0.5, 0.5, 0.23)


def moon(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.ellipse(pen.rect(0.18, 0.18, 0.82, 0.82), fill=pen.fill)
    draw.ellipse(pen.rect(0.36, 0.08, 0.96, 0.68), fill=pen.bg)


def partly_cloudy(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _sun_at(draw, pen, 0.36, 0.36, 0.15)
    _cloud(draw, pen, 0.18, 0.40, 0.80, 0.50)


def cloud(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _cloud(draw, pen, 0.05, 0.22, 0.90, 0.58)


def fog(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _cloud(draw, pen, 0.10, 0.05, 0.80, 0.48)
    for fy in (0.66, 0.78, 0.90):
        draw.line((*pen.p(0.12, fy), *pen.p(0.88, fy)), fill=pen.fill, width=pen.lw)


def _precip_cloud(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _cloud(draw, pen, 0.08, 0.04, 0.84, 0.52)


def rain(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _precip_cloud(draw, pen)
    for fx in (0.32, 0.52, 0.72):
        draw.line((*pen.p(fx, 0.64), *pen.p(fx - 0.08, 0.92)), fill=pen.fill, width=pen.lw)


def drizzle(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _precip_cloud(draw, pen)
    for fx, fy in ((0.32, 0.66), (0.52, 0.74), (0.72, 0.66), (0.42, 0.88), (0.62, 0.88)):
        draw.line((*pen.p(fx, fy), *pen.p(fx - 0.03, fy + 0.06)), fill=pen.fill, width=pen.lw)


def snow(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _precip_cloud(draw, pen)
    arm = 0.06
    for fcx, fcy in ((0.32, 0.72), (0.52, 0.84), (0.72, 0.72)):
        for a in (0, math.pi / 3, 2 * math.pi / 3):
            dx, dy = math.cos(a) * arm, math.sin(a) * arm
            draw.line((*pen.p(fcx - dx, fcy - dy), *pen.p(fcx + dx, fcy + dy)), fill=pen.fill, width=pen.lw)


def thunder(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    _precip_cloud(draw, pen)
    bolt = [(0.54, 0.56), (0.38, 0.80), (0.50, 0.80), (0.42, 0.99), (0.66, 0.72), (0.54, 0.72), (0.62, 0.56)]
    draw.polygon([pen.p(*pt) for pt in bolt], fill=pen.fill)


def drop(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.ellipse(pen.rect(0.24, 0.36, 0.76, 0.88), fill=pen.fill)
    draw.polygon([pen.p(0.5, 0.06), pen.p(0.26, 0.56), pen.p(0.74, 0.56)], fill=pen.fill)
    # highlight
    draw.arc(pen.rect(0.34, 0.46, 0.66, 0.78), 110, 190, fill=pen.bg, width=pen.lw)


def stand(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    lw = max(2, round(pen.s / 11))
    draw.ellipse(pen.rect(0.40, 0.04, 0.60, 0.24), fill=pen.fill)
    draw.line((*pen.p(0.5, 0.26), *pen.p(0.5, 0.62)), fill=pen.fill, width=lw)
    draw.line((*pen.p(0.26, 0.48), *pen.p(0.5, 0.34), *pen.p(0.74, 0.48)), fill=pen.fill, width=lw, joint="curve")
    draw.line((*pen.p(0.34, 0.94), *pen.p(0.5, 0.62), *pen.p(0.66, 0.94)), fill=pen.fill, width=lw, joint="curve")


def eye(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.chord(pen.rect(0.04, 0.22, 0.96, 0.98), 200, 340, outline=pen.fill, width=pen.lw)
    draw.chord(pen.rect(0.04, 0.02, 0.96, 0.78), 20, 160, outline=pen.fill, width=pen.lw)
    draw.ellipse(pen.rect(0.36, 0.36, 0.64, 0.64), fill=pen.fill)


def mail(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.rectangle(pen.rect(0.06, 0.20, 0.94, 0.80), outline=pen.fill, width=pen.lw)
    draw.line((*pen.p(0.06, 0.20), *pen.p(0.5, 0.54), *pen.p(0.94, 0.20)), fill=pen.fill, width=pen.lw, joint="curve")


def chat(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.rounded_rectangle(pen.rect(0.06, 0.12, 0.94, 0.68), radius=pen.s * 0.12, outline=pen.fill, width=pen.lw)
    draw.polygon([pen.p(0.24, 0.66), pen.p(0.24, 0.90), pen.p(0.46, 0.66)], fill=pen.fill)
    for fx in (0.32, 0.5, 0.68):
        cx, cy = pen.p(fx, 0.40)
        r = pen.s * 0.05
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=pen.fill)


def calendar(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.rectangle(pen.rect(0.10, 0.18, 0.90, 0.90), outline=pen.fill, width=pen.lw)
    draw.rectangle(pen.rect(0.10, 0.18, 0.90, 0.38), fill=pen.fill)
    for fx in (0.32, 0.68):
        draw.line((*pen.p(fx, 0.08), *pen.p(fx, 0.28)), fill=pen.fill, width=pen.lw * 2)


def lock(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    lw = pen.lw * 2
    draw.arc(pen.rect(0.28, 0.06, 0.72, 0.58), 180, 360, fill=pen.fill, width=lw)
    for fx in (0.28, 0.72):
        draw.line((*pen.p(fx, 0.31), *pen.p(fx, 0.46)), fill=pen.fill, width=lw)
    draw.rounded_rectangle(pen.rect(0.16, 0.44, 0.84, 0.94), radius=pen.s * 0.06, fill=pen.fill)
    draw.ellipse(pen.rect(0.43, 0.56, 0.57, 0.70), fill=pen.bg)
    draw.line((*pen.p(0.5, 0.66), *pen.p(0.5, 0.82)), fill=pen.bg, width=lw)


def power(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    lw = pen.lw * 2
    draw.arc(pen.rect(0.14, 0.18, 0.86, 0.90), 300, 240, fill=pen.fill, width=lw)
    draw.line((*pen.p(0.5, 0.08), *pen.p(0.5, 0.52)), fill=pen.fill, width=lw)


def warning(draw: ImageDraw.ImageDraw, pen: _Pen) -> None:
    draw.polygon([pen.p(0.5, 0.06), pen.p(0.96, 0.92), pen.p(0.04, 0.92)], outline=pen.fill, width=pen.lw)
    draw.line((*pen.p(0.5, 0.36), *pen.p(0.5, 0.66)), fill=pen.fill, width=pen.lw * 2)
    draw.rectangle(pen.rect(0.46, 0.74, 0.54, 0.82), fill=pen.fill)


ICONS: dict[str, IconFn] = {
    "sun": sun,
    "moon": moon,
    "partly_cloudy": partly_cloudy,
    "cloud": cloud,
    "fog": fog,
    "drizzle": drizzle,
    "rain": rain,
    "snow": snow,
    "thunder": thunder,
    "drop": drop,
    "water": drop,
    "stand": stand,
    "eye": eye,
    "mail": mail,
    "chat": chat,
    "calendar": calendar,
    "lock": lock,
    "power": power,
    "warning": warning,
}


def draw_icon(draw: ImageDraw.ImageDraw, name: str, box: Box, fill: int = BLACK, bg: int = WHITE) -> None:
    """Draw icon ``name`` into the largest square centered in ``box``."""
    size = min(box.w, box.h)
    if size < 4:
        return
    x = box.x + (box.w - size) // 2
    y = box.y + (box.h - size) // 2
    ICONS[name](draw, _Pen(x, y, size, fill, bg))


def weather_icon(code: int, is_day: bool = True) -> str:
    """Icon name for a WMO weather code (as used by Open-Meteo)."""
    if code == 0:
        return "sun" if is_day else "moon"
    if code in (1, 2):
        return "partly_cloudy" if is_day else "cloud"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "thunder"
    return "cloud"
