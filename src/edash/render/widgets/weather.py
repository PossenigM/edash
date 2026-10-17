from __future__ import annotations

from pydantic import Field

from edash.render.context import RenderContext
from edash.render.icons import draw_icon, weather_icon
from edash.render.layout import Box
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.text import draw_centered, draw_line, fit_font, line_height
from edash.render.widgets._common import draw_placeholder


class WeatherOptions(WidgetOptions):
    days: int = Field(3, ge=0, le=7)  # forecast columns after today
    show_location: bool = True


@widget("weather")
class Weather(Widget):
    Options = WeatherOptions
    topics = ("weather",)

    def render(self, ctx: RenderContext) -> None:
        o: WeatherOptions = self.options
        data = ctx.state.weather
        if data is None:
            draw_placeholder(ctx, "Waiting for weather…")
            return

        box, draw = ctx.box, ctx.draw
        today = ctx.now.date()
        today_fc = next((d for d in data.days if d.date == today), None)
        future = [d for d in data.days if d.date > today][: o.days]
        now_box, forecast_box = box.split_top(round(box.h * 0.55) if future else box.h)

        # Current conditions: icon, big temperature, today's range and location.
        icon_s = now_box.h
        draw_icon(draw, weather_icon(data.code, data.is_day), Box(0, 0, icon_s, icon_s))
        tx = icon_s + 10
        tw = max(0, box.w - tx)
        temp = f"{round(data.temperature)}°"
        temp_h = round(now_box.h * 0.6)
        temp_font = fit_font(ctx.fonts, "bold", temp, tw, temp_h, max_size=96)
        left, _, right, _ = temp_font.getbbox(temp)
        draw_centered(draw, Box(tx, 0, right - left, temp_h), temp, temp_font, measure="0°")  # left-aligned at tx

        info = []
        if today_fc:
            info.append(f"{round(today_fc.temp_max)}° / {round(today_fc.temp_min)}°")
        if o.show_location and data.location:
            info.append(data.location)
        small = ctx.fonts.get("regular", max(10, min(18, round(now_box.h * 0.18))))
        y = temp_h + 2
        for line in info:
            if y + line_height(small) > now_box.h + 4:
                break
            y += draw_line(draw, tx, y, line, small, tw)

        if not future:
            return
        col_w = forecast_box.w / len(future)
        label_font = ctx.fonts.get("bold", max(10, min(16, round(forecast_box.h * 0.24))))
        temp_small = ctx.fonts.get("regular", max(10, min(16, round(forecast_box.h * 0.24))))
        lh = line_height(label_font)
        for i, day in enumerate(future):
            x0 = round(i * col_w)
            col = Box(x0, forecast_box.y + 4, round((i + 1) * col_w) - x0, forecast_box.h - 4)
            label = day.date.strftime("%a")
            temps = f"{round(day.temp_max)}°/{round(day.temp_min)}°"
            if col.w >= col.h * 2.2:
                # Wide, short columns: icon left, day and temperatures stacked right.
                icon_s = min(col.h, round(col.w * 0.42))
                draw_icon(draw, weather_icon(day.code), Box(col.x, col.y, icon_s, col.h))
                tx, tw = col.x + icon_s + 4, col.w - icon_s - 4
                ty = col.y + (col.h - 2 * lh) // 2
                draw_line(draw, tx, ty, label, label_font, tw)
                draw_line(draw, tx, ty + lh, temps, temp_small, tw)
                continue
            draw_line(draw, col.x, col.y, label, label_font, col.w, align="center")
            icon_h = col.h - 2 * lh
            if icon_h > 6:
                draw_icon(draw, weather_icon(day.code), Box(col.x, col.y + lh, col.w, icon_h))
            draw_line(draw, col.x, col.bottom - lh, temps, temp_small, col.w, align="center")
