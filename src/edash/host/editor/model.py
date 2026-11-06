"""Editor backend: widget option descriptors, preview rendering and YAML output."""

from __future__ import annotations

import base64
import io
import os
import types
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import yaml
from pydantic.fields import FieldInfo

import edash.render.widgets  # noqa: F401  (registers the built-in widgets)
from edash.config import Config, DisplayConfig, parse_config
from edash.device.screens import ScreenSelector
from edash.errors import ConfigError
from edash.render.fonts import Fonts
from edash.render.icons import ICONS
from edash.render.layout import grid_box
from edash.render.registry import WIDGETS
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens
from edash.timeutil import TimeRange, format_duration, format_weekdays

_KINDS: dict[Any, str] = {
    bool: "bool",
    int: "int",
    float: "float",
    str: "text",
    timedelta: "duration",
    TimeRange: "timerange",
    frozenset: "weekdays",
}
_CHOICES = {("reminder", "icon"): sorted(ICONS)}


def widget_fields() -> dict[str, list[dict[str, Any]]]:
    """Form descriptors for every widget's ``options``, keyed by widget type."""
    fields = {}
    for name, cls in sorted(WIDGETS.items()):
        schema = cls.Options.model_json_schema()["properties"]
        fields[name] = [
            _describe(name, key, info, schema.get(key, {})) for key, info in cls.Options.model_fields.items()
        ]
    return fields


def _describe(widget: str, name: str, info: FieldInfo, schema: dict[str, Any]) -> dict[str, Any]:
    kind, choices, nullable = _kind(info.annotation)
    choices = _CHOICES.get((widget, name), choices)
    required = info.is_required()
    return {
        "name": name,
        "kind": "choice" if choices else kind,
        "choices": choices,
        "required": required,
        "nullable": nullable,
        "default": None if required else format_value(info.default),
        "min": _bound(schema, "minimum"),
        "max": _bound(schema, "maximum"),
    }


def _kind(annotation: Any) -> tuple[str, list[Any] | None, bool]:
    args = get_args(annotation) if get_origin(annotation) in (Union, types.UnionType) else (annotation,)
    nullable = type(None) in args
    base = next(a for a in args if a is not type(None))
    if get_origin(base) is Annotated:
        base = get_args(base)[0]
    if get_origin(base) is Literal:
        return "choice", list(get_args(base)), nullable
    return _KINDS.get(get_origin(base) or base, "text"), None, nullable


def _bound(schema: dict[str, Any], key: str) -> float | None:
    if key in schema:
        return schema[key]
    return next((s[key] for s in schema.get("anyOf", []) if key in s), None)


def format_value(value: Any) -> Any:
    if isinstance(value, timedelta):
        return format_duration(value)
    if isinstance(value, TimeRange):
        return str(value)
    if isinstance(value, frozenset):
        return format_weekdays(value)
    return value


def render_screen(data: Any, screen_id: str, now: datetime, fonts: Fonts) -> dict[str, Any]:
    """Validate ``data`` and render one screen with sample data. Raises ConfigError."""
    config = parse_config(data)
    screens, warnings = build_screens(config)
    if screen_id not in screens:
        screen_id = config.screens[0].id
    state = sample_state(now)
    result = Renderer(config.display, fonts).render(screens[screen_id], state, now)
    png = io.BytesIO()
    result.image.save(png, "PNG")
    return {
        "screen": screen_id,
        "screens": list(screens),
        "image": base64.b64encode(png.getvalue()).decode(),
        "size": result.image.size,
        "boxes": [vars(p.box) for p in screens[screen_id].widgets],
        "grid": grid_lines(config.display),
        "active_screen": ScreenSelector(config.rotation).wanted(state, now),
        "warnings": warnings + result.errors,
    }


def grid_lines(display: DisplayConfig) -> dict[str, list[tuple[int, int]]]:
    cols = [grid_box((c, 0), (1, 1), display) for c in range(display.grid.cols)]
    rows = [grid_box((0, r), (1, 1), display) for r in range(display.grid.rows)]
    return {"cols": [(b.x, b.right) for b in cols], "rows": [(b.y, b.bottom) for b in rows]}


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _represent_list(dumper: yaml.SafeDumper, data: list[Any]) -> yaml.Node:
    flow = all(isinstance(v, (str, int, float, bool)) or v is None for v in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _represent_list)


def dump_yaml(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def parse_yaml(text: str) -> Any:
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as err:
        raise ConfigError([f"YAML syntax error: {err}"]) from None


def save_config(data: Any, path: Path) -> Config:
    """Validate and write ``data``; the previous file is kept as ``<name>.bak``."""
    config = parse_config(data)
    text = dump_yaml(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_name(path.name + ".bak").write_bytes(path.read_bytes())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return config
