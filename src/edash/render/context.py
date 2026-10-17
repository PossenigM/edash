from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw

from edash.render.fonts import Fonts
from edash.render.layout import Box
from edash.state import DashboardState

# Pixel values of a mode "1" image.
BLACK = 0
WHITE = 255


@dataclass
class RenderContext:
    """What a widget gets: its own canvas (origin at its top-left), fonts, data and the time."""

    image: Image.Image
    draw: ImageDraw.ImageDraw
    fonts: Fonts
    state: DashboardState
    now: datetime

    @property
    def box(self) -> Box:
        return Box(0, 0, self.image.width, self.image.height)
