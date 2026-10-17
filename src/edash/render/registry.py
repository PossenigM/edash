"""Widget base class and registry. A new widget is a module in ``widgets/`` using ``@widget("name")``."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from edash.render.context import RenderContext
from edash.state import DashboardState


class WidgetOptions(BaseModel):
    """Base for a widget's ``options:`` block. Unknown keys are errors, to catch typos."""

    model_config = ConfigDict(extra="forbid")


class Widget:
    name: ClassVar[str]
    Options: ClassVar[type[WidgetOptions]] = WidgetOptions
    # Data topics the widget reads (documentation, and for future selective redraws).
    topics: ClassVar[tuple[str, ...]] = ()

    def __init__(self, options: WidgetOptions):
        self.options = options

    def render(self, ctx: RenderContext) -> None:
        raise NotImplementedError

    def next_update(self, state: DashboardState, now: datetime) -> datetime | None:
        """When the widget's output changes without new data (e.g. a clock). None = only on data."""
        return None


WIDGETS: dict[str, type[Widget]] = {}


def widget(name: str):
    def register(cls: type[Widget]) -> type[Widget]:
        if name in WIDGETS:
            raise RuntimeError(f"widget '{name}' registered twice")
        cls.name = name
        WIDGETS[name] = cls
        return cls

    return register


def get_widget_class(name: str) -> type[Widget]:
    import edash.render.widgets  # noqa: F401  (registers the built-in widgets)

    try:
        return WIDGETS[name]
    except KeyError:
        raise KeyError(f"unknown widget type '{name}' (available: {', '.join(sorted(WIDGETS))})") from None
