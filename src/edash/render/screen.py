from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from pydantic import ValidationError

from edash.config import DeviceConfig, WidgetConfig
from edash.errors import ConfigError, format_validation_error
from edash.render.layout import Box, check_grid_placement, grid_box
from edash.render.registry import Widget, get_widget_class


@dataclass
class PlacedWidget:
    label: str
    config: WidgetConfig
    widget: Widget
    box: Box


@dataclass
class Screen:
    id: str
    widgets: list[PlacedWidget]


def build_screens(config: DeviceConfig) -> tuple[dict[str, Screen], list[str]]:
    """Instantiate and place every widget. Raises ConfigError listing all problems; returns warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    screens: dict[str, Screen] = {}
    width, height = config.display.logical_size

    for screen_cfg in config.screens:
        placed: list[PlacedWidget] = []
        for index, widget_cfg in enumerate(screen_cfg.widgets):
            label = f"screen '{screen_cfg.id}', widget {index} ({widget_cfg.type})"
            try:
                cls = get_widget_class(widget_cfg.type)
            except KeyError as err:
                errors.append(f"{label}: {err.args[0]}")
                continue
            try:
                options = cls.Options.model_validate(widget_cfg.options)
            except ValidationError as err:
                errors.extend(f"{label}: {line}" for line in format_validation_error(err, prefix=("options",)))
                continue

            if widget_cfg.box is not None:
                box = Box(*widget_cfg.box)
            else:
                problems = check_grid_placement(widget_cfg.pos, widget_cfg.size, config.display.grid)
                if problems:
                    errors.extend(f"{label}: {p}" for p in problems)
                    continue
                box = grid_box(widget_cfg.pos, widget_cfg.size, config.display)
            if not box.fits_in(width, height) or box.w < 1 or box.h < 1:
                errors.append(f"{label}: box {box} does not fit the {width}x{height} screen")
                continue
            placed.append(PlacedWidget(label, widget_cfg, cls(options), box))

        for a, b in combinations(placed, 2):
            if a.box.overlaps(b.box):
                warnings.append(f"{a.label} overlaps {b.label.split(', ', 1)[1]}")
        screens[screen_cfg.id] = Screen(screen_cfg.id, placed)

    if errors:
        raise ConfigError(errors)
    return screens, warnings
