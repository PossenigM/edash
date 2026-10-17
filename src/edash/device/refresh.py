"""Deciding between no refresh, a partial (flicker-free) refresh and a full (flashing) one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from PIL import Image, ImageChops

Decision = Literal["none", "partial", "full"]


@dataclass(frozen=True)
class RefreshPolicy:
    full_every: timedelta
    max_partials: int
    # Large changes look cleaner with a full refresh anyway.
    full_above_fraction: float = 0.6


@dataclass
class RefreshTracker:
    last_image: Image.Image | None = None
    screen: str | None = None
    last_full: datetime | None = None
    partials: int = 0
    force_full: bool = False

    def decide(self, policy: RefreshPolicy, image: Image.Image, screen: str, now: datetime) -> Decision:
        if (
            self.force_full
            or self.last_image is None
            or screen != self.screen
            or self.last_image.size != image.size
        ):
            return "full"
        changed = ImageChops.logical_xor(self.last_image, image).getbbox()
        if changed is None:
            return "none"
        if self.last_full is None or now - self.last_full >= policy.full_every or self.partials >= policy.max_partials:
            return "full"
        x0, y0, x1, y1 = changed
        if (x1 - x0) * (y1 - y0) > policy.full_above_fraction * image.width * image.height:
            return "full"
        return "partial"

    def record(self, decision: Decision, image: Image.Image, screen: str, now: datetime) -> None:
        if decision == "none":
            return
        self.last_image = image.copy()
        self.screen = screen
        if decision == "full":
            self.last_full = now
            self.partials = 0
            self.force_full = False
        else:
            self.partials += 1
