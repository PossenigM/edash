from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from PIL import Image

log = logging.getLogger(__name__)


class Display(Protocol):
    size: tuple[int, int]

    def full(self, image: Image.Image) -> None: ...
    def partial(self, image: Image.Image) -> None: ...
    def sleep(self) -> None: ...


class WaveshareDisplay:
    """Waveshare 7.5" V2 (800x480, black/white) through the vendor's Python driver.

    Partial refreshes always cover the whole panel: the vendor's display_Partial
    streams a complete frame and the controller only flips pixels that changed.
    The panel stays initialised between partial refreshes; sleep() is called on
    shutdown.
    """

    def __init__(self) -> None:
        from waveshare_epd import epd7in5_V2  # installed on the Pi by pi/install.sh

        self._epd = epd7in5_V2.EPD()
        self.size = (self._epd.width, self._epd.height)
        self._mode: str | None = None

    def full(self, image: Image.Image) -> None:
        self._epd.init()
        self._epd.display(self._epd.getbuffer(image))
        self._mode = "full"

    def partial(self, image: Image.Image) -> None:
        if self._mode != "partial":
            self._epd.init_part()
            self._mode = "partial"
        self._epd.display_Partial(self._epd.getbuffer(image), 0, 0, self.size[0], self.size[1])

    def sleep(self) -> None:
        if self._mode is not None:
            self._epd.sleep()
            self._mode = None


class FileDisplay:
    """Writes frames to a PNG instead of a panel: for running the device on a desktop."""

    def __init__(self, path: Path, size: tuple[int, int] = (800, 480)):
        self.path = path
        self.size = size
        self.counts = {"full": 0, "partial": 0}

    def full(self, image: Image.Image) -> None:
        self._write(image, "full")

    def partial(self, image: Image.Image) -> None:
        self._write(image, "partial")

    def sleep(self) -> None:
        pass

    def _write(self, image: Image.Image, kind: str) -> None:
        tmp = self.path.with_suffix(".tmp.png")
        image.save(tmp)
        os.replace(tmp, self.path)
        self.counts[kind] += 1
        log.info("%s refresh -> %s", kind, self.path)
