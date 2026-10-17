from datetime import timedelta

import pytest

from edash.device.app import DeviceApp
from edash.link import Received
from edash.protocol import Ack, Command, ConfigMsg, Error, Hello, MailData, MailMsg, TimeSync
from tests.conftest import FakeDisplay


class FakeClock:
    def __init__(self, now):
        self._now = now
        self.synced = False

    def now(self):
        return self._now

    def sync(self, host_now):
        self._now = host_now
        self.synced = True


@pytest.fixture
def app(now):
    def no_port():
        raise OSError("no port in tests")

    app = DeviceApp(FakeDisplay(), no_port, clock=FakeClock(now))
    app.sent = []
    app.connection.send = app.sent.append
    return app


def deliver(app, *messages):
    for seq, message in enumerate(messages, start=1):
        app._handle(Received(message.model_copy(update={"seq": seq})))


def test_waiting_screen_then_config_and_data(app, example_config, now):
    app.step(max_wait=0)
    assert app.display.frames == ["full"] and app._refresh.screen == "waiting"

    deliver(app, Hello(role="host"), TimeSync(now=now), ConfigMsg(config=example_config.device_payload()))
    assert isinstance(app.sent[0], Hello) and isinstance(app.sent[-1], Ack)
    app.step(max_wait=0)
    assert app._refresh.screen == "main" and app.display.frames[-1] == "full"

    deliver(app, MailMsg(data=MailData(unread_count=2)))
    app.step(max_wait=0)
    assert app.display.frames[-1] == "partial"


def test_invalid_config_is_rejected_and_old_one_kept(app, example_config):
    deliver(app, ConfigMsg(config=example_config.device_payload()))
    bad = example_config.device_payload()
    bad["screens"][0]["widgets"][0]["type"] = "nope"
    deliver(app, ConfigMsg(config=bad))
    assert isinstance(app.sent[-1], Error) and "unknown widget type" in app.sent[-1].message
    assert "main" in app.screens


def test_screen_override_and_auto(app, example_config):
    deliver(app, ConfigMsg(config=example_config.device_payload()))
    deliver(app, Command(action="screen", arg="idle"))
    app.step(max_wait=0)
    assert app._refresh.screen == "idle"
    deliver(app, Command(action="screen", arg="auto"))
    app.step(max_wait=0)
    assert app._refresh.screen == "main"
    deliver(app, Command(action="screen", arg="missing"))
    assert isinstance(app.sent[-1], Error)


def test_rule_switches_to_meeting_screen(app, example_config, now):
    from edash.protocol import CalendarData, CalendarMsg, Event

    deliver(app, ConfigMsg(config=example_config.device_payload()))
    app.step(max_wait=0)
    start = now + timedelta(minutes=4)
    deliver(app, CalendarMsg(data=CalendarData(events=[Event(subject="Sync", start=start, end=start + timedelta(minutes=30))])))
    app.clock._now = now + timedelta(minutes=3)  # past min_dwell since the first selection
    app.step(max_wait=0)
    assert app._refresh.screen == "meeting"


def test_presence_switches_to_away_screen_and_back(app, example_config, now):
    from edash.protocol import Presence

    deliver(app, ConfigMsg(config=example_config.device_payload()))
    app.step(max_wait=0)
    deliver(app, Presence(away=True, reason="sleep", since=now))
    app.step(max_wait=0)
    assert app._refresh.screen == "_away" and app.display.frames[-1] == "full"
    assert app._next_wake is None  # the away screen has nothing that changes by itself

    deliver(app, Presence(away=False))
    app.step(max_wait=0)
    assert app._refresh.screen == "main"


def test_away_wins_over_manual_override(app, example_config, now):
    from edash.protocol import Presence

    deliver(app, ConfigMsg(config=example_config.device_payload()), Command(action="screen", arg="idle"))
    deliver(app, Presence(away=True, reason="locked", since=now))
    app.step(max_wait=0)
    assert app._refresh.screen == "_away"
