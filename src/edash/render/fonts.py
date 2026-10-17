"""Font lookup. Drop ``regular.ttf`` and ``bold.ttf`` into ``edash/assets/fonts/`` to use your own."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import ImageFont

log = logging.getLogger(__name__)

ASSET_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_CANDIDATES: dict[str, list[Path]] = {
    "regular": [
        ASSET_FONTS / "regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),  # Debian / Raspberry Pi OS
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),  # Arch
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ],
    "bold": [
        ASSET_FONTS / "bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ],
}

Font = ImageFont.FreeTypeFont


class Fonts:
    def __init__(self, paths: dict[str, Path | None] | None = None):
        self._paths = paths if paths is not None else {role: _find(role) for role in _CANDIDATES}
        self._cache: dict[tuple[str, int], Font] = {}

    def get(self, role: str = "regular", size: int = 16) -> Font:
        key = (role, size)
        font = self._cache.get(key)
        if font is None:
            path = self._paths.get(role)
            font = ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size)
            self._cache[key] = font
        return font


def _find(role: str) -> Path | None:
    for path in _CANDIDATES[role]:
        if path.is_file():
            return path
    log.warning("no %s font found, falling back to Pillow's built-in font", role)
    return None
