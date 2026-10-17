"""JSON-lines transport over a serial port, shared by host and device."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from edash.protocol import Message, _Message, decode, encode

log = logging.getLogger(__name__)


class Stream(Protocol):
    """What we need from a pyserial ``Serial`` (read with a timeout)."""

    def read(self, size: int = 1) -> bytes: ...
    def write(self, data: bytes) -> int | None: ...
    def close(self) -> None: ...


class ProtocolError(Exception):
    """A line arrived that is not a valid message."""


class LineLink:
    MAX_LINE = 1 << 20

    def __init__(self, stream: Stream):
        self._stream = stream
        self._buffer = bytearray()
        self._seq = 0
        self._write_lock = threading.Lock()

    def send(self, message: _Message) -> int:
        with self._write_lock:
            self._seq += 1
            self._stream.write(encode(message.model_copy(update={"seq": self._seq})))
            flush = getattr(self._stream, "flush", None)
            if flush:
                flush()
            return self._seq

    def receive(self) -> Message | None:
        """Return the next message, or None if the stream's read timeout expired first."""
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._buffer[:newline]).strip()
                del self._buffer[: newline + 1]
                if not line:
                    continue
                try:
                    return decode(line)
                except ValidationError as err:
                    preview = line[:80].decode("utf-8", "replace")
                    raise ProtocolError(f"invalid message {preview!r}: {err.error_count()} error(s)") from None

            waiting = getattr(self._stream, "in_waiting", 0) or 1
            chunk = self._stream.read(waiting)
            if not chunk:
                return None
            self._buffer += chunk
            if len(self._buffer) > self.MAX_LINE and b"\n" not in self._buffer:
                self._buffer.clear()
                raise ProtocolError("line too long, discarded")


@dataclass(frozen=True)
class Connected:
    pass


@dataclass(frozen=True)
class Disconnected:
    reason: str


@dataclass(frozen=True)
class Received:
    message: Message


@dataclass(frozen=True)
class Invalid:
    error: str


LinkEvent = Connected | Disconnected | Received | Invalid


class Connection:
    """Keeps a LineLink open on streams from ``opener``, reconnecting after errors.

    Events are delivered to ``on_event`` from a background thread.
    """

    def __init__(
        self,
        opener: Callable[[], Stream],
        on_event: Callable[[LinkEvent], None],
        *,
        retry_interval: float = 3.0,
        name: str = "link",
    ):
        self._opener = opener
        self._on_event = on_event
        self._retry_interval = retry_interval
        self._name = name
        self._link: LineLink | None = None
        self._stream: Stream | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self._link is not None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f"{self._name}-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def send(self, message: _Message) -> bool:
        """Send if connected. Write failures are logged, not raised; the reader notices dead ports."""
        link = self._link
        if link is None:
            return False
        try:
            link.send(message)
            return True
        except Exception as err:
            log.debug("%s: send of %s failed: %s", self._name, message.__class__.__name__, err)
            return False

    def _run(self) -> None:
        last_error = None
        while not self._stop.is_set():
            try:
                stream = self._opener()
            except Exception as err:
                if str(err) != last_error:
                    log.info("%s: not connected (%s)", self._name, err)
                    last_error = str(err)
                self._stop.wait(self._retry_interval)
                continue

            last_error = None
            self._stream, self._link = stream, LineLink(stream)
            self._on_event(Connected())
            reason = "stopped"
            try:
                while not self._stop.is_set():
                    try:
                        message = self._link.receive()
                    except ProtocolError as err:
                        self._on_event(Invalid(str(err)))
                        continue
                    if message is not None:
                        self._on_event(Received(message))
            except Exception as err:
                reason = str(err) or err.__class__.__name__
            finally:
                self._link = self._stream = None
                try:
                    stream.close()
                except Exception:
                    pass
                self._on_event(Disconnected(reason))
            self._stop.wait(self._retry_interval)
