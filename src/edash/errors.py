from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError


class ConfigError(Exception):
    """One or more problems in a configuration, as human-readable messages."""

    def __init__(self, messages: Sequence[str], source: str | None = None):
        self.messages = list(messages)
        self.source = source
        super().__init__(str(self))

    def __str__(self) -> str:
        head = f"invalid config ({self.source})" if self.source else "invalid config"
        return head + ":\n" + "\n".join(f"  - {m}" for m in self.messages)


def format_validation_error(err: ValidationError, prefix: Sequence[str | int] = ()) -> list[str]:
    """Turn a pydantic error into lines like ``screens.0.widgets.2.pos: Field required``."""
    lines = []
    for e in err.errors():
        loc = ".".join(str(p) for p in (*prefix, *e["loc"]))
        msg = e["msg"].removeprefix("Value error, ")
        lines.append(f"{loc}: {msg}" if loc else msg)
    return lines
