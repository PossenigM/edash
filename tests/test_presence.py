from datetime import timedelta

from edash.host.presence import PresenceTracker


def test_lock_and_unlock(now):
    tracker = PresenceTracker()
    message = tracker.handle("lock", now)
    assert (message.away, message.reason, message.since) == (True, "locked", now)
    assert tracker.handle("lock", now + timedelta(minutes=1)) is None  # nothing changed
    assert tracker.handle("unlock", now + timedelta(minutes=5)).away is False


def test_sleep_while_locked_then_resume_still_locked(now):
    tracker = PresenceTracker()
    tracker.handle("lock", now)
    asleep = tracker.handle("suspend", now + timedelta(minutes=2))
    assert asleep.reason == "sleep" and asleep.since == now + timedelta(minutes=2)

    resumed = tracker.handle("resume", now + timedelta(hours=8))
    assert resumed.reason == "locked" and resumed.since == now  # original lock time
    assert tracker.handle("unlock", now + timedelta(hours=8, minutes=1)).away is False


def test_shutdown_wins_over_stopped(now):
    tracker = PresenceTracker()
    assert tracker.handle("shutdown", now).reason == "shutdown"
    assert tracker.handle("stopped", now + timedelta(seconds=2)) is None


def test_resume_without_sleep_is_ignored(now):
    tracker = PresenceTracker()
    assert tracker.handle("resume", now) is None
    assert tracker.message().away is False and not tracker.away
