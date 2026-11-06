import pytest
from PIL import ImageChops

from edash.config import DeviceConfig
from edash.render.logo import logo_image
from edash.render.preview import render_preview
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens


@pytest.mark.parametrize("size", [16, 48, 128])
def test_logo_image(size):
    image = logo_image(size)
    assert image.mode == "1" and image.size == (size, size)

    def at(x, y):
        return image.getpixel((round(x * size / 64), round(y * size / 64)))

    assert at(9, 32) == 0  # inverted left part of the tile
    assert at(52, 20) == 255  # light right part
    assert image.getpixel((0, 0)) == 255  # rounded corner


def _render(widget, now):
    config = DeviceConfig.model_validate({"screens": [{"id": "s", "widgets": [widget]}]})
    screens, _ = build_screens(config)
    return Renderer(config.display).render(screens["s"], sample_state(now), now)


def test_logo_widget_text_follows_the_mark(now):
    plain = _render({"type": "logo", "pos": [0, 0], "size": [12, 2], "options": {"align": "left"}}, now)
    named = _render(
        {"type": "logo", "pos": [0, 0], "size": [12, 2], "options": {"text": "eDash", "align": "left"}}, now
    )
    assert not plain.errors and not named.errors
    diff = ImageChops.logical_xor(plain.image, named.image).getbbox()
    mark = plain.image.point(lambda v: 255 - v).getbbox()
    assert diff is not None and diff[0] > mark[2]


def test_builtin_away_screen_shows_the_logo(example_config, now, tmp_path):
    screens, _ = build_screens(example_config)
    assert [p.config.type for p in screens["_away"].widgets] == ["away", "logo"]
    _, notes = render_preview(example_config, tmp_path, screen_ids=["_away"], now=now)
    assert notes == []
