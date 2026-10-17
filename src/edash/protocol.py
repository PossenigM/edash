"""Messages exchanged between host and device: one JSON object per line.

Host -> device: hello, time, config, mail, calendar, teams, weather, presence, command.
Device -> host: hello, ack, error, status.

The host re-sends its full snapshot whenever a connection is (re)established,
so every message is idempotent and the device never needs to persist anything.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

from edash import PROTOCOL_VERSION, __version__


class _Model(BaseModel):
    # Ignore unknown fields so a newer host can talk to an older device.
    model_config = ConfigDict(extra="ignore")


# --- data payloads ---------------------------------------------------------


class MailItem(_Model):
    sender: str
    subject: str
    received: AwareDatetime
    important: bool = False


class MailData(_Model):
    unread_count: int = 0
    items: list[MailItem] = Field(default_factory=list)


class Event(_Model):
    subject: str
    start: AwareDatetime
    end: AwareDatetime
    location: str | None = None
    all_day: bool = False
    online: bool = False
    tentative: bool = False


class CalendarData(_Model):
    events: list[Event] = Field(default_factory=list)


class ChatItem(_Model):
    chat: str
    sender: str
    preview: str
    at: AwareDatetime
    unread: bool = True


class TeamsData(_Model):
    unread_count: int = 0
    items: list[ChatItem] = Field(default_factory=list)


class WeatherDay(_Model):
    date: date
    code: int  # WMO weather code
    temp_max: float
    temp_min: float
    precip_prob: int | None = None


class WeatherData(_Model):
    location: str | None = None
    temperature: float
    code: int
    is_day: bool = True
    units: Literal["C", "F"] = "C"
    days: list[WeatherDay] = Field(default_factory=list)


# --- messages --------------------------------------------------------------


class _Message(_Model):
    seq: int = 0


class Hello(_Message):
    type: Literal["hello"] = "hello"
    role: Literal["host", "device"]
    version: str = __version__
    protocol: int = PROTOCOL_VERSION


class TimeSync(_Message):
    type: Literal["time"] = "time"
    now: AwareDatetime


class ConfigMsg(_Message):
    type: Literal["config"] = "config"
    config: dict[str, Any]  # validated as DeviceConfig on the device


class _DataMessage(_Message):
    # When the host fetched the data, and until when it counts as current. The
    # host re-sends cached data periodically, so the arrival time says nothing
    # about freshness; widgets show an "as of" marker once fresh_until passes.
    fetched_at: AwareDatetime | None = None
    fresh_until: AwareDatetime | None = None


class MailMsg(_DataMessage):
    type: Literal["mail"] = "mail"
    data: MailData


class CalendarMsg(_DataMessage):
    type: Literal["calendar"] = "calendar"
    data: CalendarData


class TeamsMsg(_DataMessage):
    type: Literal["teams"] = "teams"
    data: TeamsData


class WeatherMsg(_DataMessage):
    type: Literal["weather"] = "weather"
    data: WeatherData


class Presence(_Message):
    """Whether the user is at the laptop. While away, the device shows the away screen."""

    type: Literal["presence"] = "presence"
    away: bool
    reason: str | None = None  # "locked", "sleep", "shutdown", "stopped"
    since: AwareDatetime | None = None


class Command(_Message):
    type: Literal["command"] = "command"
    action: Literal["screen", "refresh", "status"]
    arg: str | None = None


class Ack(_Message):
    type: Literal["ack"] = "ack"
    ref: int


class Error(_Message):
    type: Literal["error"] = "error"
    ref: int | None = None
    message: str


class Status(_Message):
    type: Literal["status"] = "status"
    screen: str | None
    clock_synced: bool
    partial_refreshes: int
    last_full_refresh: AwareDatetime | None
    uptime_s: float


DataMessage = MailMsg | CalendarMsg | TeamsMsg | WeatherMsg
DATA_TOPICS = ("mail", "calendar", "teams", "weather")

Message = Annotated[
    Union[Hello, TimeSync, ConfigMsg, MailMsg, CalendarMsg, TeamsMsg, WeatherMsg, Presence, Command, Ack, Error, Status],
    Field(discriminator="type"),
]
_message_adapter: TypeAdapter[Message] = TypeAdapter(Message)


def encode(message: _Message) -> bytes:
    return message.model_dump_json().encode("utf-8") + b"\n"


def decode(line: bytes | str) -> Message:
    """Parse one line; raises pydantic.ValidationError on malformed input."""
    return _message_adapter.validate_json(line)
