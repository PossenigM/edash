"""Parsing of Graph and Open-Meteo responses, with canned JSON instead of the network."""

from datetime import timedelta

from edash.config import CalendarSourceConfig, MailSourceConfig, TeamsSourceConfig, WeatherSourceConfig
from edash.host.graph import parse_graph_datetime
from edash.host.sources import CalendarSource, MailSource, TeamsSource, WeatherSource, html_to_text


class FakeGraph:
    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, path, params=None, headers=None):
        self.calls.append((path, params))
        return self.responses[path]

    def get_all(self, path, params=None, headers=None, limit=200):
        return self.get(path, params, headers)["value"]


POLL = timedelta(minutes=1)


def test_parse_graph_datetime():
    assert parse_graph_datetime("2026-10-19T07:30:00.0000000").utcoffset() == timedelta(0)
    assert parse_graph_datetime("2026-10-19T07:30:00.1234567Z").microsecond == 123456
    assert parse_graph_datetime("2026-10-19T09:30:00+02:00").hour == 9


def test_mail(now):
    graph = FakeGraph(
        {
            "/me/mailFolders/inbox": {"unreadItemCount": 12},
            "/me/mailFolders/inbox/messages": {
                "value": [
                    {"subject": "Hi", "from": {"emailAddress": {"name": "Ann"}}, "receivedDateTime": "2026-10-19T07:00:00Z", "importance": "high"},
                    {"subject": None, "from": None, "receivedDateTime": "2026-10-19T06:00:00Z"},
                ]
            },
        }
    )
    data = MailSource(MailSourceConfig(), graph, POLL).fetch(now).data
    assert data.unread_count == 12
    assert [(m.sender, m.subject, m.important) for m in data.items] == [("Ann", "Hi", True), ("Unknown sender", "(no subject)", False)]


def test_calendar_skips_cancelled_and_declined(now):
    def event(subject, **extra):
        return {
            "subject": subject,
            "start": {"dateTime": "2026-10-19T08:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-10-19T08:30:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": "Room 1"},
            **extra,
        }

    graph = FakeGraph(
        {
            "/me/calendarView": {
                "value": [
                    event("Keep", responseStatus={"response": "tentativelyAccepted"}, isOnlineMeeting=True),
                    event("Cancelled", isCancelled=True),
                    event("Declined", responseStatus={"response": "declined"}),
                ]
            }
        }
    )
    events = CalendarSource(CalendarSourceConfig(), graph, POLL).fetch(now).data.events
    assert [e.subject for e in events] == ["Keep"]
    assert events[0].tentative and events[0].online and events[0].location == "Room 1"
    assert events[0].start.astimezone(now.tzinfo).hour == 10


def test_teams_unread_detection(now):
    def chat(topic, sender_id, sender, created, read_at):
        return {
            "topic": topic,
            "viewpoint": {"lastMessageReadDateTime": read_at},
            "lastMessagePreview": {
                "createdDateTime": created,
                "from": {"user": {"id": sender_id, "displayName": sender}},
                "body": {"contentType": "html", "content": "<p>Hello &amp; welcome</p>"},
            },
        }

    graph = FakeGraph(
        {
            "/me": {"id": "me"},
            "/me/chats": {
                "value": [
                    chat(None, "u1", "Sam", "2026-10-19T07:30:00Z", "2026-10-19T07:00:00Z"),  # unread
                    chat("Team", "u2", "Kim", "2026-10-19T06:00:00Z", "2026-10-19T06:30:00Z"),  # read
                    chat("Mine", "me", "Me", "2026-10-19T05:00:00Z", None),  # my own message
                ]
            },
        }
    )
    data = TeamsSource(TeamsSourceConfig(), graph, POLL).fetch(now).data
    assert data.unread_count == 1
    assert [(c.chat, c.unread) for c in data.items] == [("Sam", True), ("Team", False), ("Mine", False)]
    assert data.items[0].preview == "Hello & welcome"


def test_html_to_text():
    assert html_to_text("<div>a<br>b</div>&nbsp;c") == "a b c"


def test_weather(now):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "current": {"temperature_2m": 12.4, "weather_code": 61, "is_day": 1},
                "daily": {
                    "time": ["2026-10-19", "2026-10-20"],
                    "weather_code": [61, 0],
                    "temperature_2m_max": [14.0, 16.5],
                    "temperature_2m_min": [6.0, None],
                    "precipitation_probability_max": [80, 5],
                },
            }

    class Session:
        def get(self, url, params, timeout):
            assert params["latitude"] == 48.1
            return Response()

    data = WeatherSource(WeatherSourceConfig(latitude=48.1, longitude=11.5, name="Home"), Session()).fetch(now).data
    assert (data.location, data.temperature, data.code) == ("Home", 12.4, 61)
    assert len(data.days) == 1  # the day with a missing value is skipped


def test_graph_throttling_reports_retry_after():
    import pytest

    from edash.host.graph import GraphClient, GraphError

    class Response:
        def __init__(self, status, headers):
            self.status_code, self.headers, self.text = status, headers, ""

        def json(self):
            return {"error": {"message": "Too many requests"}}

    class Session:
        def __init__(self, response):
            self.response = response

        def get(self, *args, **kwargs):
            return self.response

    class Auth:
        def token(self):
            return "t"

    with pytest.raises(GraphError) as info:
        GraphClient(Auth(), Session(Response(429, {"Retry-After": "30"}))).get("/me/messages")
    assert info.value.retry_after == 30 and "Too many requests" in str(info.value)

    with pytest.raises(GraphError) as info:
        GraphClient(Auth(), Session(Response(503, {}))).get("/me")
    assert info.value.retry_after == 60  # default when the header is missing

    with pytest.raises(GraphError) as info:
        GraphClient(Auth(), Session(Response(403, {}))).get("/me")
    assert info.value.retry_after is None


def test_demo_sources_produce_sample_data(now):
    from edash.host.sources import DemoSource

    messages = {topic: DemoSource(topic).fetch(now) for topic in ("mail", "calendar", "teams")}
    assert messages["mail"].data.unread_count > 0
    assert messages["calendar"].data.events
    assert messages["teams"].data.items
