from datetime import timedelta

from PIL import Image, ImageDraw

from edash.device.refresh import RefreshPolicy, RefreshTracker

POLICY = RefreshPolicy(full_every=timedelta(minutes=30), max_partials=3)


def frame(dots: int = 0, big: bool = False) -> Image.Image:
    image = Image.new("1", (800, 480), 255)
    draw = ImageDraw.Draw(image)
    for i in range(dots):
        draw.point((10 + i, 10), fill=0)
    if big:
        draw.rectangle((0, 0, 799, 400), fill=0)
    return image


def test_first_frame_and_screen_change_are_full(now):
    tracker = RefreshTracker()
    assert tracker.decide(POLICY, frame(), "main", now) == "full"
    tracker.record("full", frame(), "main", now)
    assert tracker.decide(POLICY, frame(1), "idle", now) == "full"


def test_unchanged_small_change_and_limits(now):
    tracker = RefreshTracker()
    tracker.record("full", frame(), "main", now)
    assert tracker.decide(POLICY, frame(), "main", now) == "none"

    for i in range(1, 4):
        assert tracker.decide(POLICY, frame(i), "main", now) == "partial"
        tracker.record("partial", frame(i), "main", now)
    assert tracker.decide(POLICY, frame(5), "main", now) == "full"  # max_partials reached


def test_periodic_and_large_change_full(now):
    tracker = RefreshTracker()
    tracker.record("full", frame(), "main", now)
    assert tracker.decide(POLICY, frame(1), "main", now + timedelta(minutes=31)) == "full"
    assert tracker.decide(POLICY, frame(big=True), "main", now) == "full"


def test_force_full(now):
    tracker = RefreshTracker()
    tracker.record("full", frame(), "main", now)
    tracker.force_full = True
    assert tracker.decide(POLICY, frame(), "main", now) == "full"
    tracker.record("full", frame(), "main", now)
    assert not tracker.force_full
