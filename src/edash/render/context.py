from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw

from edash.render.fonts import Fonts
from edash.render.i18n import EN, Locale
from edash.render.layout import Box
from edash.state import DashboardState

BLACK = 0
WHITE = 255


@dataclass
class RenderContext:
    """What a widget gets: its own canvas (origin at its top-left), fonts, data, the time and the language."""

    image: Image.Image
    draw: ImageDraw.ImageDraw
    fonts: Fonts
    state: DashboardState
    now: datetime
    locale: Locale = EN

    @property
    def box(self) -> Box:
        return Box(0, 0, self.image.width, self.image.height)
