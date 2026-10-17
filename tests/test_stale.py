from datetime import timedelta

from edash.config import BUILTIN_AWAY_SCREEN, parse_config
from edash.protocol import MailData, MailMsg
from edash.render.renderer import Renderer
from edash.render.sample import sample_state
from edash.render.screen import build_screens
from edash.state import DashboardState

FRESH = timedelta(minutes=10)


def mail(now, count=1, fetched=None):
    fetched = fetched or now
    return MailMsg(data=MailData(unread_count=count), fetched_at=fetched, fresh_until=fetched + FRESH)


def test_apply_tracks_fetch_time_and_staleness(now):
    state = DashboardState()
    assert state.apply(mail(now), now)
    assert state.fetched["mail"] == now
    assert not state.is_stale("mail", now + timedelta(minutes=9))
    assert state.is_stale("mail", now + timedelta(minutes=10))


def test_resend_of_old_data_stays_stale(now):
    state = DashboardState()
    old = mail(now)
    state.apply(old, now)
    later = now + timedelta(minutes=30)
    assert not state.apply(old, later)  # same data, same fetch time: still stale, nothing to redraw
    assert state.is_stale("mail", later)


def test_fresh_copy_of_same_data_triggers_redraw(now):
    state = DashboardState()
    later = now + timedelta(minutes=30)
    state.apply(mail(now), now)
    assert state.apply(mail(now, fetched=later), later)  # marker must disappear
    assert not state.is_stale("mail", later)


def test_messages_without_freshness_never_go_stale(now):
    state = DashboardState()
    state.apply(MailMsg(data=MailData()), now)
    assert not state.is_stale("mail", now + timedelta(days=1))


def _marker_pixels(image, box) -> int:
    """Black pixels in the top-right 120x20 of a widget box, where the marker sits."""
    region = image.crop((box.right - 120, box.y, box.right, box.y + 20))
    return region.histogram()[0]  # mode "1": bin 0 counts black pixels


def test_marker_drawn_only_when_stale(example_config, now):
    screens, _ = build_screens(example_config)
    main = screens["main"]
    mail_widget = next(p for p in main.widgets if p.config.type == "mail")
    renderer = Renderer(example_config.display)

    fresh = sample_state(now)
    stale = sample_state(now)
    stale.fresh_until["mail"] = now - timedelta(minutes=1)
    stale.fetched["mail"] = now - timedelta(minutes=31)

    assert _marker_pixels(renderer.render(main, fresh, now).image, mail_widget.box) == 0
    assert _marker_pixels(renderer.render(main, stale, now).image, mail_widget.box) > 50


def test_show_stale_false_hides_marker(example_config, now):
    data = example_config.model_dump(mode="json")
    for w in data["screens"][0]["widgets"]:
        w["show_stale"] = False
    config = parse_config(data)
    screens, _ = build_screens(config)
    main = screens["main"]
    mail_widget = next(p for p in main.widgets if p.config.type == "mail")
    stale = sample_state(now)
    stale.fresh_until["mail"] = now - timedelta(minutes=1)
    assert _marker_pixels(Renderer(config.display).render(main, stale, now).image, mail_widget.box) == 0


def test_next_update_wakes_when_data_turns_stale(example_config, now):
    screens, _ = build_screens(example_config)
    state = sample_state(now)
    turns_stale = now + timedelta(seconds=20)
    state.fresh_until["teams"] = turns_stale
    assert Renderer(example_config.display).next_update(screens["main"], state, now) == turns_stale


def test_builtin_away_screen_renders_every_reason(example_config, now):
    from edash.state import Away

    screens, _ = build_screens(example_config)
    renderer = Renderer(example_config.display)
    for reason in ("locked", "sleep", "shutdown", "stopped", None):
        state = sample_state(now)
        state.away = Away(reason, now - timedelta(hours=1))
        assert renderer.render(screens[BUILTIN_AWAY_SCREEN], state, now).errors == []
