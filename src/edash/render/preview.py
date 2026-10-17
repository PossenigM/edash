"""Render screens to PNG files on the desktop, without the Pi."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from PIL import Image

from edash.config import DeviceConfig
from edash.errors import ConfigError
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens
from edash.state import DashboardState


def render_preview(
    config: DeviceConfig,
    out_dir: Path,
    *,
    screen_ids: Iterable[str] | None = None,
    now: datetime | None = None,
    state: DashboardState | None = None,
    scale: int = 1,
) -> tuple[list[Path], list[str]]:
    """Write ``preview-<screen>.png`` files; returns the paths and any warnings/render errors."""
    screens, notes = build_screens(config)
    now = now or datetime.now().astimezone()
    state = state or sample_state(now)
    ids = list(screen_ids or screens)
    unknown = [s for s in ids if s not in screens]
    if unknown:
        raise ConfigError([f"unknown screen '{s}' (available: {', '.join(screens)})" for s in unknown])

    renderer = Renderer(config.display)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for screen_id in ids:
        result = renderer.render(screens[screen_id], state, now)
        notes.extend(result.errors)
        image = result.image
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        path = out_dir / f"preview-{screen_id}.png"
        image.save(path)
        paths.append(path)
    return paths, notes
