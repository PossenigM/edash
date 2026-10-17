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


def test_second_instance_is_refused(tmp_path, app):
    import socket

    from edash.host.app import AlreadyRunning

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app.config.host.control_port = port
    app.open_control_server()
    try:
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other = HostApp(app.config_path, FakePlatform(other_dir))
        other.config.host.control_port = port
        with pytest.raises(AlreadyRunning, match=f"port {port} is in use"):
            other.open_control_server()
    finally:
        app._server.server_close()


def test_connect_sends_hello_and_snapshot_follows_device_hello(app):
    from edash.link import Connected, Received
    from edash.protocol import Hello

    app._on_event(Connected())
    assert [type(m) for m in app.sent] == [Hello]
    app.sent.clear()
    app._on_event(Received(Hello(role="device")))
    assert [type(m) for m in app.sent][:3] == [TimeSync, ConfigMsg, Presence]


def test_protocol_mismatch_is_logged_once(app, caplog):
    from edash.link import Received
    from edash.protocol import Hello

    for _ in range(2):
        app._on_event(Received(Hello(role="device", protocol=99)))
    assert sum("protocol 99" in r.message for r in caplog.records) == 1


def test_throttled_source_waits_for_retry_after(app):
    import time

    from edash.host.graph import GraphError

    class Throttled(Source):
        topic = "mail"

        def fetch(self, now):
            raise GraphError("HTTP 429", retry_after=120)

    item = _Scheduled(Throttled(timedelta(minutes=1)))
    before = time.monotonic()
    app._run_source(item)
    assert item.status == "throttled, retrying in 120 s"
    assert item.next_run - before == pytest.approx(120, abs=1)


def test_demo_mode_replaces_graph_sources(tmp_path):
    config = tmp_path / "config.yaml"
    shutil.copyfile(EXAMPLE_CONFIG, config)
    app = HostApp(config, FakePlatform(tmp_path), demo=True)
    assert sorted(item.source.topic for item in app._scheduled) == ["calendar", "mail", "teams", "weather"]
