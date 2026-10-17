"""Optional tray icon (pystray). The host works the same without it."""

from __future__ import annotations

import threading

from PIL import Image, ImageDraw

from edash.host.app import HostApp


def _icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 10, 60, 54), radius=6, fill="white", outline="black", width=4)
    for y in (22, 32, 42):
        draw.line((14, y, 50, y), fill="black", width=4)
    return image


def run_with_tray(app: HostApp) -> None:
    import pystray
    from pystray import Menu, MenuItem as Item

    worker = threading.Thread(target=app.run, name="host", daemon=True)
    worker.start()

    def screen_action(screen_id: str):
        return lambda icon, item: app.control({"action": "screen", "arg": screen_id})

    def screen_items():
        yield Item("Automatic", screen_action("auto"))
        for screen_id in app.screen_ids():
            yield Item(screen_id, screen_action(screen_id))

    def quit_app(icon, item) -> None:
        app.stop()
        icon.stop()

    menu = Menu(
        Item("Refresh display", lambda icon, item: app.control({"action": "refresh"})),
        Item("Fetch data now", lambda icon, item: app.control({"action": "fetch"})),
        Item("Screen", Menu(screen_items)),
        Item("Open config", lambda icon, item: app.platform.open_file(app.config_path)),
        Menu.SEPARATOR,
        Item("Quit", quit_app),
    )
    pystray.Icon("edash", _icon_image(), "eDash", menu).run()
    app.stop()
    worker.join(timeout=5)
