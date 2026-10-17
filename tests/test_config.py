import copy

import pytest
import yaml

from edash.config import EXAMPLE_CONFIG, DeviceConfig, parse_config
from edash.errors import ConfigError


@pytest.fixture
def raw():
    return yaml.safe_load(EXAMPLE_CONFIG.read_text())


def errors_for(data) -> list[str]:
    with pytest.raises(ConfigError) as info:
        parse_config(data)
    return info.value.messages


def test_example_config_is_valid(example_config):
    assert [s.id for s in example_config.screens] == ["main", "meeting", "idle"]
    assert example_config.rotation.default == "main"


def test_device_payload_round_trips(example_config):
    payload = example_config.device_payload()
    assert set(payload) == {"display", "screens", "rotation"}
    device = DeviceConfig.model_validate(payload)
    assert device.display.full_refresh_every == example_config.display.full_refresh_every
    assert device.rotation == example_config.rotation


def test_rotation_defaults_to_first_screen(raw):
    del raw["rotation"]
    assert parse_config(raw).rotation.default == "main"


def test_unknown_widget_type(raw):
    raw["screens"][0]["widgets"][0]["type"] = "clokc"
    [message] = errors_for(raw)
    assert "unknown widget type 'clokc'" in message and "screen 'main', widget 0" in message


def test_bad_widget_option_is_reported_with_path(raw):
    raw["screens"][0]["widgets"][2]["options"]["every"] = "soon"
    [message] = errors_for(raw)
    assert "widget 2 (reminder): options.every: invalid duration" in message


def test_typo_in_widget_option(raw):
    raw["screens"][0]["widgets"][0]["options"] = {"time_fromat": "%H:%M"}
    assert "options.time_fromat" in errors_for(raw)[0]


def test_widget_outside_grid(raw):
    raw["screens"][0]["widgets"][0]["pos"] = [10, 0]
    assert "exceeds the 12x8 grid" in errors_for(raw)[0]


def test_box_and_pos_are_exclusive(raw):
    raw["screens"][0]["widgets"][0]["box"] = [0, 0, 100, 100]
    assert "not both" in errors_for(raw)[0]


def test_pixel_box_must_fit(raw):
    widget = raw["screens"][0]["widgets"][0]
    del widget["pos"], widget["size"]
    widget["box"] = [700, 0, 200, 100]
    assert "does not fit the 800x480 screen" in errors_for(raw)[0]


def test_rotation_rule_to_unknown_screen(raw):
    raw["rotation"]["rules"][0]["screen"] = "nope"
    assert "unknown screens: nope" in errors_for(raw)[0]


def test_invalid_rule_condition(raw):
    raw["rotation"]["rules"][0]["when"] = "coffee_level < 3"
    assert "unknown variable 'coffee_level'" in errors_for(raw)[0]


def test_multiple_errors_are_collected(raw):
    data = copy.deepcopy(raw)
    data["screens"][0]["widgets"][0]["type"] = "nope"
    data["screens"][1]["widgets"][0]["pos"] = [11, 0]
    assert len(errors_for(data)) == 2


def test_screen_ids_with_underscore_are_reserved(raw):
    raw["screens"][2]["id"] = "_idle"
    assert "reserved: _idle" in errors_for(raw)[0]


def test_custom_away_screen_replaces_builtin(raw):
    from edash.render.screen import build_screens

    raw["rotation"]["away_screen"] = "idle"
    screens, _ = build_screens(parse_config(raw))
    assert "_away" not in screens

    raw["rotation"]["away_screen"] = "nope"
    assert "unknown screens: nope" in errors_for(raw)[0]
