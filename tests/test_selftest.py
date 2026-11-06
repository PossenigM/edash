import itertools

import pytest
from PIL import ImageChops

from edash.device.main import main as device_main
from edash.device.selftest import SelftestReport, run_selftest
from tests.conftest import FakeDisplay


def fake_clock(step: float = 0.5):
    ticks = itertools.count(step=step)
    return lambda: next(ticks)


def test_sequence_timing_and_sleep(now):
    display = FakeDisplay()
    pauses = []
    report = run_selftest(display, partial_steps=4, pause=2.0, sleep=pauses.append, clock=fake_clock(), now=now)

    assert display.frames == ["full", "partial", "partial", "partial", "partial", "full"]
    assert pauses == [2.0] * 5
    assert report.full_s == [0.5, 0.5] and report.partial_s == [0.5] * 4
    assert display.asleep
    assert all(img.size == (800, 480) and img.mode == "1" for img in display.images)


def test_each_partial_step_changes_the_frame(now):
    display = FakeDisplay()
    run_selftest(display, partial_steps=3, pause=0, sleep=lambda s: None, now=now)
    frames = display.images
    for before, after in zip(frames, frames[1:], strict=False):
        assert ImageChops.logical_xor(before, after).getbbox() is not None


@pytest.mark.parametrize("rotation", [90, 270])
def test_rotated_pattern_still_fits_the_panel(rotation, now):
    display = FakeDisplay()
    run_selftest(display, rotation=rotation, partial_steps=1, pause=0, sleep=lambda s: None, now=now)
    assert {img.size for img in display.images} == {(800, 480)}


def test_rotation_moves_the_up_arrow(now):
    """The arrow tip sits at the top center of the logical canvas; check where it lands on the panel."""
    tips = {}
    for rotation in (0, 90, 180, 270):
        display = FakeDisplay()
        run_selftest(display, rotation=rotation, partial_steps=1, pause=0, sleep=lambda s: None, now=now)
        image = display.images[0]
        w, h = image.size
        probes = {"top": (w // 2, 14), "right": (w - 14, h // 2), "bottom": (w // 2, h - 14), "left": (14, h // 2)}
        tips[rotation] = {side for side, xy in probes.items() if image.getpixel(xy) == 0}
    assert tips == {0: {"top"}, 90: {"right"}, 180: {"bottom"}, 270: {"left"}}


def test_summary_text():
    assert SelftestReport().summary() == ""
    report = SelftestReport(full_s=[4.0, 3.0], partial_s=[0.4, 0.8])
    assert report.summary() == "full refresh 3.50 s · partial refresh avg 0.60 s (max 0.80 s, 2x)"


def test_cli_selftest_with_file_display(tmp_path, capsys):
    out = tmp_path / "frame.png"
    device_main(["--selftest", "--display", "file", "--out", str(out), "--partial-steps", "2", "--pause", "0"])
    assert out.exists()
    assert "Self-test done: full refresh" in capsys.readouterr().out
