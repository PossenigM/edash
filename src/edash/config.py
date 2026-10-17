"""Configuration schema.

One YAML file lives on the host. Its ``display``, ``screens`` and ``rotation``
sections form the :class:`DeviceConfig` that is pushed to the Pi; ``host`` and
``sources`` are only used on the laptop.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from edash.errors import ConfigError, format_validation_error
from edash.timeutil import Duration

EXAMPLE_CONFIG = Path(__file__).parent / "assets" / "config.example.yaml"

# Built-in screen shown while the user is away, unless rotation.away_screen names another.
BUILTIN_AWAY_SCREEN = "_away"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- device part -----------------------------------------------------------


class GridConfig(_Model):
    cols: int = Field(12, ge=1)
    rows: int = Field(8, ge=1)
    gap: int = Field(8, ge=0)
    margin: int = Field(12, ge=0)


class DisplayConfig(_Model):
    width: int = Field(800, gt=0)
    height: int = Field(480, gt=0)
    # Degrees the rendered image is turned clockwise before it goes to the panel.
    rotation: Literal[0, 90, 180, 270] = 0
    full_refresh_every: Duration = timedelta(minutes=30)
    max_partial_refreshes: int = Field(60, ge=0)
    grid: GridConfig = Field(default_factory=GridConfig)

    @property
    def logical_size(self) -> tuple[int, int]:
        """Size of the canvas widgets are laid out on (portrait when rotated by 90/270)."""
        if self.rotation in (90, 270):
            return self.height, self.width
        return self.width, self.height


class WidgetConfig(_Model):
    type: str
    pos: tuple[int, int] | None = None  # grid cell (col, row)
    size: tuple[int, int] | None = None  # grid cells (cols, rows)
    box: tuple[int, int, int, int] | None = None  # pixels (x, y, w, h), instead of pos/size
    title: str | None = None
    frame: bool = False
    show_stale: bool = True  # "as of 09:12" marker when the widget's data is outdated
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_placement(self) -> WidgetConfig:
        if self.box is not None:
            if self.pos is not None or self.size is not None:
                raise ValueError("use either 'box' (pixels) or 'pos' + 'size' (grid cells), not both")
        elif self.pos is None or self.size is None:
            raise ValueError("a widget needs 'pos' and 'size' (grid cells) or 'box' (pixels)")
        return self


class ScreenConfig(_Model):
    id: str
    widgets: list[WidgetConfig] = Field(default_factory=list)


class RuleConfig(_Model):
    when: str
    screen: str

    @field_validator("when")
    @classmethod
    def _check_condition(cls, value: str) -> str:
        from edash.rules import parse_condition

        parse_condition(value)
        return value


class RotationConfig(_Model):
    default: str
    rules: list[RuleConfig] = Field(default_factory=list)
    # Minimum time on a screen before a rule may switch away (avoids flapping full refreshes).
    min_dwell: Duration = timedelta(minutes=2)
    # Shown while the laptop is locked, asleep or shut down. Default: a built-in away screen.
    away_screen: str | None = None

    @property
    def away_screen_id(self) -> str:
        return self.away_screen or BUILTIN_AWAY_SCREEN


class DeviceConfig(_Model):
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    screens: list[ScreenConfig] = Field(min_length=1)
    rotation: RotationConfig | None = None

    @model_validator(mode="after")
    def _check_screens(self) -> DeviceConfig:
        ids = [s.id for s in self.screens]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate screen ids: {', '.join(dupes)}")
        reserved = [i for i in ids if i.startswith("_")]
        if reserved:
            raise ValueError(f"screen ids starting with '_' are reserved: {', '.join(reserved)}")
        if self.rotation is None:
            self.rotation = RotationConfig(default=ids[0])
        refs = [self.rotation.default, *(r.screen for r in self.rotation.rules)]
        if self.rotation.away_screen:
            refs.append(self.rotation.away_screen)
        unknown = sorted({r for r in refs if r not in ids})
        if unknown:
            raise ValueError(f"rotation refers to unknown screens: {', '.join(unknown)}")
        return self


# --- host part -------------------------------------------------------------


class HostConfig(_Model):
    port: str = "auto"  # "auto", or e.g. "COM5" / "/dev/edash"
    time_sync_every: Duration = timedelta(minutes=5)
    resend_every: Duration = timedelta(minutes=10)
    control_port: int = Field(47811, ge=1024, le=65535)
    proxy: str | None = None  # e.g. "http://proxy.corp:8080"


class GraphConfig(_Model):
    client_id: str | None = None
    tenant: str = "organizations"
    poll: Duration = timedelta(seconds=60)


class MailSourceConfig(_Model):
    enabled: bool = True
    folder: str = "inbox"
    max_items: int = Field(8, ge=1, le=50)
    poll: Duration | None = None  # default: graph.poll


class CalendarSourceConfig(_Model):
    enabled: bool = True
    lookahead: Duration = timedelta(days=2)
    include_declined: bool = False
    poll: Duration | None = None


class TeamsSourceConfig(_Model):
    enabled: bool = True
    max_items: int = Field(8, ge=1, le=50)
    poll: Duration | None = None


class WeatherSourceConfig(_Model):
    enabled: bool = True
    name: str | None = None  # label shown on the display
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    days: int = Field(4, ge=1, le=16)  # forecast days including today
    units: Literal["C", "F"] = "C"
    poll: Duration = timedelta(minutes=15)


class SourcesConfig(_Model):
    graph: GraphConfig = Field(default_factory=GraphConfig)
    mail: MailSourceConfig = Field(default_factory=MailSourceConfig)
    calendar: CalendarSourceConfig = Field(default_factory=CalendarSourceConfig)
    teams: TeamsSourceConfig = Field(default_factory=TeamsSourceConfig)
    weather: WeatherSourceConfig | None = None


class Config(DeviceConfig):
    """The whole config file as used on the host."""

    host: HostConfig = Field(default_factory=HostConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)

    def device_config(self) -> DeviceConfig:
        return DeviceConfig.model_validate(self.device_payload())

    def device_payload(self) -> dict[str, Any]:
        """JSON-ready device part, as sent to the Pi."""
        return self.model_dump(mode="json", include={"display", "screens", "rotation"})


def parse_config(data: Any, *, source: str | None = None) -> Config:
    """Validate a parsed config, including every widget's options and placement."""
    try:
        config = Config.model_validate(data)
    except ValidationError as err:
        raise ConfigError(format_validation_error(err), source=source) from None

    from edash.render.screen import build_screens

    try:
        build_screens(config)
    except ConfigError as err:
        raise ConfigError(err.messages, source=source) from None
    return config


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ConfigError([str(err)], source=str(path)) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ConfigError([f"YAML syntax error: {err}"], source=str(path)) from None
    return parse_config(data or {}, source=str(path))
