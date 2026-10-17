"""HostApp behaviour without a serial port: messages go to a list instead."""

import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from edash.config import EXAMPLE_CONFIG
from edash.host.app import HostApp, _Scheduled
from edash.host.platform.base import Platform
from edash.host.sources import Source
from edash.protocol import ConfigMsg, MailData, MailMsg, Presence, TimeSync


class FakePlatform(Platform):
    name = "fake"

    def __init__(self, root: Path):
        self.root = root

    def cache_dir(self) -> Path:
        return self.root

    def install_autostart(self, config_path):
        return []

    def uninstall_autostart(self):
        return []

    def open_file(self, path):
        pass


class FakeMailSource(Source):
    topic = "mail"

    def fetch(self, now):
        return MailMsg(data=MailData(unread_count=3))


@pytest.fixture
def app(tmp_path):
    config = tmp_path / "config.yaml"
    shutil.copyfile(EXAMPLE_CONFIG, config)
    app = HostApp(config, FakePlatform(tmp_path))
    app.sent = []
    app.connection.send = lambda message: app.sent.append(message) or True
    return app


def test_fetched_data_is_stamped_with_freshness(app):
    item = _Scheduled(FakeMailSource(timedelta(minutes=1)))
    app._run_source(item)
    [message] = app.sent
    assert message.fetched_at is not None
    assert message.fresh_until - message.fetched_at == timedelta(minutes=10)  # max(3 x 1 min, 10 min)
    assert item.status == "ok"


def test_system_events_send_presence_once(app):
    app.on_system_event("lock")
    app.on_system_event("lock")
    app.on_system_event("unlock")
    assert [(m.away, m.reason) for m in app.sent] == [(True, "locked"), (False, None)]


def test_snapshot_includes_presence(app):
    app.on_system_event("suspend")
    app.sent.clear()
    app._send_snapshot()
    kinds = [type(m) for m in app.sent]
    assert kinds[:3] == [TimeSync, ConfigMsg, Presence]
    assert app.sent[2].reason == "sleep"
