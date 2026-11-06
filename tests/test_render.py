from datetime import timedelta

import pytest

from edash.config import DisplayConfig
from edash.render.preview import render_preview
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens
from edash.state import DashboardState


@pytest.mark.parametrize("offset_h", [0, 2.5, 9, 14])  # morning, midday, evening, night
def test_all_screens_render_without_widget_errors(example_config, now, offset_h):
    at = now + timedelta(hours=offset_h)
    screens, warnings = build_screens(example_config)
    assert warnings == []
    renderer = Renderer(example_config.display)
    for screen in screens.values():
        result = renderer.render(screen, sample_state(at), at)
        assert result.errors == []
        assert result.image.size == (800, 480) and result.image.mode == "1"


def test_screens_render_before_any_data_arrives(example_config, now):
    screens, _ = build_screens(example_config)
    renderer = Renderer(example_config.display)
    for screen in screens.values():
        assert renderer.render(screen, DashboardState(), now).errors == []


def test_next_update_is_next_minute_with_clock(example_config, now):
    screens, _ = build_screens(example_config)
    renderer = Renderer(example_config.display)
    assert renderer.next_update(screens["main"], sample_state(now), now) == now.replace(minute=41)


def test_rotation_turns_image_for_panel():
    renderer = Renderer(DisplayConfig(rotation=90))
    from PIL import Image

    assert renderer.to_panel(Image.new("1", (480, 800))).size == (800, 480)


def test_preview_writes_pngs(example_config, now, tmp_path):
    paths, notes = render_preview(example_config, tmp_path, now=now, scale=2)
    assert [p.name for p in paths] == [
        "preview-main.png",
        "preview-meeting.png",
        "preview-idle.png",
        "preview-_away.png",
    ]
    assert notes == []
    from PIL import Image

    assert Image.open(paths[0]).size == (1600, 960)
