from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edash.config import EXAMPLE_CONFIG, load_config

CEST = timezone(timedelta(hours=2))


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 19, 9, 40, tzinfo=CEST)  # a Monday


@pytest.fixture
def example_config():
    return load_config(EXAMPLE_CONFIG)


class FakeStream:
    """In-memory stand-in for a pyserial port: feed() what the peer sends, read written bytes."""

    def __init__(self, chunks: list[bytes] | None = None):
        self.incoming = list(chunks or [])
        self.written = bytearray()
        self.closed = False

    def feed(self, data: bytes) -> None:
        self.incoming.append(data)

    def read(self, size: int = 1) -> bytes:
        return self.incoming.pop(0) if self.incoming else b""

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_stream() -> FakeStream:
    return FakeStream()


class FakeDisplay:
    """Records refreshes instead of driving a panel."""

    size = (800, 480)

    def __init__(self):
        self.frames: list[str] = []
        self.images = []
        self.asleep = False

    def full(self, image):
        self.frames.append("full")
        self.images.append(image.copy())

    def partial(self, image):
        self.frames.append("partial")
        self.images.append(image.copy())

    def sleep(self):
        self.asleep = True
