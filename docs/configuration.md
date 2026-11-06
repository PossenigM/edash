# Configuration

The configuration is a single YAML file on the host. The `display`, `screens` and
`rotation` sections are sent to the Pi; `host` and `sources` are used on the host only.
[`config.example.yaml`](../src/edash/assets/config.example.yaml) lists every section
with comments.

Validation errors name the exact location, for example:

```
screen 'main', widget 2 (reminder): options.every: invalid duration 'soon'
```

| Value type | Format |
|---|---|
| Duration | `30s`, `45m`, `1h30m`, `2d` |
| Time window | `"08:00-17:00"`; may wrap past midnight (`"22:00-06:00"`) |
| Weekdays | `mon-fri`, `sat,sun` |

## Display

| Key | Default | Description |
|---|---|---|
| `language` | `en` | `en` or `de`: day and month names and widget texts |
| `rotation` | `0` | `90`, `180`, `270` for a rotated panel (clockwise) |
| `full_refresh_every` | `30m` | Interval for a full refresh, which clears ghosting |
| `max_partial_refreshes` | `60` | Partial refreshes before a full one is forced |
| `grid` | `12×8`, gap 8, margin 12 | Layout grid: `{ cols, rows, gap, margin }` |

## Screens and widgets

Each screen has an `id` and a list of widgets. Screen ids starting with `_` are
reserved for built-in screens.

```yaml
screens:
  - id: main
    widgets:
      - { type: clock,    pos: [0, 0], size: [4, 2] }
      - { type: calendar, pos: [0, 2], size: [5, 6], title: Today, frame: true }
      - { type: text,     box: [600, 400, 200, 80], options: { text: "Do not disturb", invert: true } }
```

| Key | Description |
|---|---|
| `type` | Widget type, see below |
| `pos`, `size` | Grid placement: `[col, row]` and `[cols, rows]` |
| `box` | Pixel placement `[x, y, w, h]`, instead of `pos`/`size` |
| `title` | Title bar text |
| `frame` | Draw a border |
| `show_stale` | Mark outdated data (default `true`) |
| `options` | Widget-specific options; unknown keys are rejected |

### Widget types

| Type | Content | Options |
|---|---|---|
| `clock` | Time and date | `time_format`, `date_format` (strftime, `null` hides the date), `date_ratio` |
| `weather` | Current conditions and forecast | `days`, `show_location` |
| `calendar` | Agenda; running meeting inverted | `days`, `max_items`, `font_size`, `show_location`, `show_past`, `empty_text` |
| `next_meeting` | Running or next meeting with countdown | `lookahead`, `empty_text` |
| `mail` | Unread mail | `max_items`, `font_size`, `show_header`, `empty_text` |
| `teams` | Recent chats, unread marked | `max_items`, `font_size`, `show_header`, `unread_only`, `empty_text` |
| `reminder` | Recurring reminder, inverted when due | `label`, `every`, `active`, `days`, `highlight_for`, `icon`, `due_text` |
| `text` | Static text | `text`, `size`, `bold`, `align`, `invert` |
| `logo` | eDash logo, optionally followed by a text | `text`, `align` |
| `status` | Host connection and last update | `font_size`, `align` |
| `away` | Away reason and next meeting, for custom away screens | `title`, `message`, `show_next_meeting` |

Reminder icons: `calendar`, `chat`, `cloud`, `drizzle`, `drop`, `eye`, `fog`, `lock`,
`mail`, `moon`, `partly_cloudy`, `power`, `rain`, `snow`, `stand`, `sun`, `thunder`,
`warning`, `water`.

Reminders are stateless: they are due every `every` from the start of the `active`
window, so reboots and reconnects do not shift the schedule.

## Screen rotation

The first matching rule selects the screen; otherwise `default` is shown.
`min_dwell` is the minimum time on a screen before a rule may switch away.

```yaml
rotation:
  default: main
  min_dwell: 2m
  rules:
    - { when: "meeting_starts_in <= 5m", screen: meeting }
    - { when: "time in 18:30-07:00 and not meeting_active", screen: idle }
```

| Condition | Type |
|---|---|
| `meeting_active`, `host_connected` | flag |
| `meeting_starts_in` | duration |
| `unread_mail`, `unread_teams` | count |
| `time in HH:MM-HH:MM` | time window |
| `weekday in ...` | weekdays |

Durations and counts are compared with `<`, `<=`, `>`, `>=`, `==`, `!=`. Clauses are
combined with `and` and negated with `not`.

## Away screen

While the laptop is locked, suspended or shut down, or the host has stopped, the
display shows the built-in away screen with the reason, the time since, the next
meeting and the logo. It has no clock: the Pi may lose power together with the laptop, and a
frozen clock would show a wrong time. `rotation.away_screen` selects a custom screen
instead; the `away` widget provides the same content there.

## Outdated data

Each data message carries `fetched_at` and `fresh_until` (three poll intervals, at
least 10 minutes). After `fresh_until`, the widget shows an inverted "as of 09:12"
label. The next successful fetch removes it.

## Language

`display.language` sets day and month names and all widget texts. `%A`, `%a`, `%B`
and `%b` in `time_format` and `date_format` follow this setting, independent of the
system locale. Translations are in `src/edash/render/i18n.py`.

## Fonts

`regular.ttf` and `bold.ttf` in `src/edash/assets/fonts/` replace the default
DejaVu Sans. Fonts designed for legibility without antialiasing work best on the
1-bit panel, e.g. Atkinson Hyperlegible or Inter.
