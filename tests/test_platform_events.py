import sys
import threading

import pytest

from edash.host.platform.logind import LogindWatcher, event_for


@pytest.mark.parametrize(
    ("interface", "member", "body", "event"),
    [
        ("org.freedesktop.login1.Manager", "PrepareForSleep", (True,), "suspend"),
        ("org.freedesktop.login1.Manager", "PrepareForSleep", (False,), "resume"),
        ("org.freedesktop.login1.Manager", "PrepareForShutdown", (True,), "shutdown"),
        ("org.freedesktop.login1.Manager", "PrepareForShutdown", (False,), None),
        ("org.freedesktop.login1.Session", "Lock", (), "lock"),
        ("org.freedesktop.login1.Session", "Unlock", (), "unlock"),
        (
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            ("org.freedesktop.login1.Session", {"LockedHint": ("b", True)}, []),
            "lock",
        ),
        (
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            ("org.freedesktop.login1.Session", {"LockedHint": ("b", False)}, []),
            "unlock",
        ),
        (
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            ("org.freedesktop.login1.Session", {"IdleHint": ("b", True)}, []),
            None,
        ),
        ("org.freedesktop.login1.Manager", "SessionNew", ("2", "/x"), None),
    ],
)
def test_logind_event_mapping(interface, member, body, event):
    assert event_for(interface, member, body) == event


class FakeFd:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self):
        self.calls = 0

    def send_and_get_reply(self, msg, timeout=None):
        self.calls += 1
        return type("Reply", (), {"body": (FakeFd(),)})()


def test_logind_holds_then_releases_on_suspend_and_retakes_on_resume():
    events = []
    watcher = LogindWatcher(events.append, hold_s=0)
    conn = FakeConn()
    watcher._inhibit(conn)
    lock = watcher._inhibitor

    watcher._dispatch(conn, "suspend")
    assert events == ["suspend"] and lock.closed and not watcher.inhibiting

    watcher._dispatch(conn, "resume")
    assert events == ["suspend", "resume"] and watcher.inhibiting and conn.calls == 2

    watcher._dispatch(conn, "lock")  # lock does not touch the inhibitor
    assert watcher.inhibiting and conn.calls == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_watcher_receives_posted_messages():
    from edash.host.platform import windows_events as we

    we.HOLD_S.clear()  # no delays in the test
    received = []
    done = threading.Event()

    def callback(event):
        received.append(event)
        if len(received) == 4:
            done.set()

    watcher = we.WindowsEventWatcher(callback).start()
    try:
        assert watcher.hwnd
        post = watcher._user32.PostMessageW
        post(watcher.hwnd, we.WM_WTSSESSION_CHANGE, we.WTS_SESSION_LOCK, 0)
        post(watcher.hwnd, we.WM_POWERBROADCAST, we.PBT_APMSUSPEND, 0)
        post(watcher.hwnd, we.WM_POWERBROADCAST, we.PBT_APMRESUMEAUTOMATIC, 0)
        post(watcher.hwnd, we.WM_WTSSESSION_CHANGE, we.WTS_SESSION_UNLOCK, 0)
        assert done.wait(5)
    finally:
        watcher.stop()
    assert received == ["lock", "suspend", "resume", "unlock"]
    assert watcher.hwnd is None
