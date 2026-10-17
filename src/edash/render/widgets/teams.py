from __future__ import annotations

from pydantic import Field

from edash.render.context import RenderContext
from edash.render.registry import Widget, WidgetOptions, widget
from edash.render.widgets._common import Row, draw_message_list, draw_placeholder, short_time


class TeamsOptions(WidgetOptions):
    max_items: int = Field(5, ge=1, le=20)
    font_size: int = Field(15, ge=8, le=40)
    show_header: bool = True
    unread_only: bool = False
    empty_text: str | None = None  # default: "No new messages" in the display language


@widget("teams")
class Teams(Widget):
    Options = TeamsOptions
    topics = ("teams",)

    def render(self, ctx: RenderContext) -> None:
        o: TeamsOptions = self.options
        loc = ctx.locale
        data = ctx.state.teams
        if data is None:
            draw_placeholder(ctx, loc.t("waiting_teams"))
            return
        chats = [c for c in data.items if c.unread or not o.unread_only]
        rows = [
            Row(
                c.chat,
                c.preview if c.sender == c.chat else f"{c.sender}: {c.preview}",
                short_time(c.at, ctx.now, loc),
                "• " if c.unread else "",
            )
            for c in chats
        ]
        draw_message_list(
            ctx,
            icon="chat",
            header=loc.plural("unread_chats", data.unread_count),
            rows=rows,
            max_items=o.max_items,
            font_size=o.font_size,
            show_header=o.show_header,
            empty_text=o.empty_text or loc.t("no_messages"),
        )
