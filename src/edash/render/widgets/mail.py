from __future__ import annotations

from pydantic import Field

from edash.render.context import RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.widgets._common import Row, draw_message_list, draw_placeholder, short_time


class MailOptions(WidgetOptions):
    max_items: int = Field(5, ge=1, le=20)
    font_size: int = Field(15, ge=8, le=40)
    show_header: bool = True
    empty_text: str | None = None  # default: "Inbox zero" in the display language


@widget("mail")
class Mail(Widget):
    Options = MailOptions
    topics = ("mail",)

    def render(self, ctx: RenderContext) -> None:
        o: MailOptions = self.options
        loc = ctx.locale
        data = ctx.state.mail
        if data is None:
            draw_placeholder(ctx, loc.t("waiting_mail"))
            return
        rows = [
            Row(m.sender, m.subject, short_time(m.received, ctx.now, loc), "! " if m.important else "")
            for m in data.items
        ]
        draw_message_list(
            ctx,
            icon="mail",
            header=loc.t("unread", n=data.unread_count),
            rows=rows,
            max_items=o.max_items,
            font_size=o.font_size,
            show_header=o.show_header,
            empty_text=o.empty_text or loc.t("inbox_zero"),
        )
