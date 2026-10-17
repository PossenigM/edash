from datetime import date, timedelta

import pytest
import yaml

from edash.config import EXAMPLE_CONFIG, parse_config
from edash.render.i18n import DE, EN, LOCALES
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens


def test_names_do_not_depend_on_system_locale(now):
    assert DE.strftime(now, "%A, %d. %B") == "Montag, 19. Oktober"
    assert DE.strftime(now, "%a %H:%M") == "Mo 09:40"
    assert EN.strftime(now, "%A, %d %B") == "Monday, 19 October"
    assert DE.strftime(date(2026, 3, 1), "%b") == "Mär"


def test_percent_escapes_and_other_codes_pass_through(now):
    assert DE.strftime(now, "100%% %A %Y") == "100% Montag 2026"


def test_when_and_plural(now):
    assert DE.when(now - timedelta(hours=1), now) == "08:40"
    assert DE.when(now + timedelta(days=1), now) == "Di 09:40"
    assert DE.plural("unread_chats", 1) == "1 ungelesener Chat"
    assert EN.plural("unread_chats", 3) == "3 unread chats"


def test_all_languages_have_the_same_keys():
    keys = {lang: set(loc.strings) for lang, loc in LOCALES.items()}
    assert keys["de"] == keys["en"]
    for loc in LOCALES.values():
        assert len(loc.days) == len(loc.days_short) == 7
        assert len(loc.months) == len(loc.months_short) == 12


@pytest.mark.parametrize("language", sorted(LOCALES))
def test_every_screen_renders_in_every_language(language, now):
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw["display"]["language"] = language
    config = parse_config(raw)
    screens, _ = build_screens(config)
    renderer = Renderer(config.display)
    for screen in screens.values():
        assert renderer.render(screen, sample_state(now), now).errors == []


def test_unknown_language_is_a_config_error():
    from edash.errors import ConfigError

    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw["display"]["language"] = "fr"
    with pytest.raises(ConfigError, match="display.language"):
        parse_config(raw)
