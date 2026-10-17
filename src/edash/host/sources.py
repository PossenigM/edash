"""Data sources on the host. Each one fetches a topic and returns a ready-to-send message."""

from __future__ import annotations

import html
import logging
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import ClassVar

import requests

from edash.config import (
    CalendarSourceConfig,
    Config,
    MailSourceConfig,
    TeamsSourceConfig,
    WeatherSourceConfig,
)
from edash.host.graph import GraphAuth, GraphClient, NotLoggedIn, parse_graph_datetime
from edash.host.platform import Platform
from edash.protocol import (
    CalendarData,
    CalendarMsg,
    ChatItem,
    DataMessage,
    Event,
    MailData,
    MailItem,
    MailMsg,
    TeamsData,
    TeamsMsg,
    WeatherData,
    WeatherDay,
    WeatherMsg,
)
from edash.timeutil import start_of_day

log = logging.getLogger(__name__)


class Source(ABC):
    topic: ClassVar[str]

    def __init__(self, interval: timedelta):
        self.interval = interval

    @abstractmethod
    def fetch(self, now: datetime) -> DataMessage: ...


class WeatherSource(Source):
    """Open-Meteo: free, no API key."""

    topic = "weather"
    URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, config: WeatherSourceConfig, session: requests.Session):
        super().__init__(config.poll)
        self.config = config
        self.session = session

    def fetch(self, now: datetime) -> WeatherMsg:
        c = self.config
        response = self.session.get(
            self.URL,
            params={
                "latitude": c.latitude,
                "longitude": c.longitude,
                "current": "temperature_2m,weather_code,is_day",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": c.days,
                "temperature_unit": "fahrenheit" if c.units == "F" else "celsius",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        current, daily = payload["current"], payload["daily"]
        precip = daily.get("precipitation_probability_max") or [None] * len(daily["time"])
        days = [
            WeatherDay(date=date.fromisoformat(d), code=int(code), temp_max=hi, temp_min=lo, precip_prob=p)
            for d, code, hi, lo, p in zip(
                daily["time"], daily["weather_code"], daily["temperature_2m_max"], daily["temperature_2m_min"], precip
            )
            if None not in (code, hi, lo)
        ]
        return WeatherMsg(
            data=WeatherData(
                location=c.name,
                temperature=current["temperature_2m"],
                code=int(current["weather_code"]),
                is_day=bool(current.get("is_day", 1)),
                units=c.units,
                days=days,
            )
        )


class MailSource(Source):
    topic = "mail"

    def __init__(self, config: MailSourceConfig, graph: GraphClient, default_poll: timedelta):
        super().__init__(config.poll or default_poll)
        self.config = config
        self.graph = graph

    def fetch(self, now: datetime) -> MailMsg:
        folder = f"/me/mailFolders/{self.config.folder}"
        unread = self.graph.get(folder, {"$select": "unreadItemCount"}).get("unreadItemCount", 0)
        messages = self.graph.get(
            f"{folder}/messages",
            {
                # Graph wants $orderby properties to also appear first in $filter.
                "$filter": "receivedDateTime ge 1900-01-01T00:00:00Z and isRead eq false",
                "$orderby": "receivedDateTime desc",
                "$top": self.config.max_items,
                "$select": "subject,from,receivedDateTime,importance",
            },
        ).get("value", [])
        items = [
            MailItem(
                sender=((m.get("from") or {}).get("emailAddress") or {}).get("name") or "Unknown sender",
                subject=m.get("subject") or "(no subject)",
                received=parse_graph_datetime(m["receivedDateTime"]),
                important=m.get("importance") == "high",
            )
            for m in messages
        ]
        return MailMsg(data=MailData(unread_count=unread, items=items))


class CalendarSource(Source):
    topic = "calendar"

    def __init__(self, config: CalendarSourceConfig, graph: GraphClient, default_poll: timedelta):
        super().__init__(config.poll or default_poll)
        self.config = config
        self.graph = graph

    def fetch(self, now: datetime) -> CalendarMsg:
        start = start_of_day(now)
        raw = self.graph.get_all(
            "/me/calendarView",
            {
                "startDateTime": start.isoformat(),
                "endDateTime": (now + self.config.lookahead).isoformat(),
                "$select": "subject,start,end,location,isAllDay,isOnlineMeeting,isCancelled,responseStatus,showAs",
                "$orderby": "start/dateTime",
                "$top": 50,
            },
            headers={"Prefer": 'outlook.timezone="UTC"'},
        )
        events = []
        for e in raw:
            response = (e.get("responseStatus") or {}).get("response")
            if e.get("isCancelled") or (response == "declined" and not self.config.include_declined):
                continue
            events.append(
                Event(
                    subject=e.get("subject") or "(no title)",
                    start=parse_graph_datetime(e["start"]["dateTime"]),
                    end=parse_graph_datetime(e["end"]["dateTime"]),
                    location=((e.get("location") or {}).get("displayName") or None),
                    all_day=bool(e.get("isAllDay")),
                    online=bool(e.get("isOnlineMeeting")),
                    tentative=response == "tentativelyAccepted" or e.get("showAs") == "tentative",
                )
            )
        return CalendarMsg(data=CalendarData(events=events))


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(content: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", content)).split())


class TeamsSource(Source):
    """Recent 1:1 and group chats (Chat.Read). Channel posts would need admin consent."""

    topic = "teams"

    def __init__(self, config: TeamsSourceConfig, graph: GraphClient, default_poll: timedelta):
        super().__init__(config.poll or default_poll)
        self.config = config
        self.graph = graph
        self._my_id: str | None = None

    def fetch(self, now: datetime) -> TeamsMsg:
        if self._my_id is None:
            self._my_id = self.graph.get("/me", {"$select": "id"})["id"]
        chats = self.graph.get(
            "/me/chats",
            {
                "$expand": "lastMessagePreview",
                "$orderby": "lastMessagePreview/createdDateTime desc",
                "$top": min(50, self.config.max_items * 2),
            },
        ).get("value", [])

        items = []
        for chat in chats:
            preview = chat.get("lastMessagePreview")
            if not preview or preview.get("isDeleted"):
                continue
            sender = (preview.get("from") or {}).get("user") or {}
            sender_name = sender.get("displayName") or "Someone"
            at = parse_graph_datetime(preview["createdDateTime"])
            read_at = (chat.get("viewpoint") or {}).get("lastMessageReadDateTime")
            unread = sender.get("id") != self._my_id and (read_at is None or at > parse_graph_datetime(read_at))
            items.append(
                ChatItem(
                    chat=chat.get("topic") or sender_name,
                    sender=sender_name,
                    preview=html_to_text((preview.get("body") or {}).get("content") or "") or "(attachment)",
                    at=at,
                    unread=unread,
                )
            )
        items = items[: self.config.max_items]
        return TeamsMsg(data=TeamsData(unread_count=sum(i.unread for i in items), items=items))


def build_sources(config: Config, session: requests.Session, platform: Platform) -> list[Source]:
    s = config.sources
    sources: list[Source] = []
    if s.weather and s.weather.enabled:
        sources.append(WeatherSource(s.weather, session))

    wanted = [(cfg, cls) for cfg, cls in ((s.mail, MailSource), (s.calendar, CalendarSource), (s.teams, TeamsSource)) if cfg.enabled]
    if not wanted:
        return sources
    try:
        graph = GraphClient(GraphAuth(s.graph, platform.token_cache_path(), platform, session), session)
    except NotLoggedIn as err:
        log.warning("mail, calendar and Teams are disabled: %s", err)
        return sources
    sources.extend(cls(cfg, graph, s.graph.poll) for cfg, cls in wanted)
    return sources
