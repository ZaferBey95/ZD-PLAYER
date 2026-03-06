from __future__ import annotations

import os

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")

from gi.repository import GdkPixbuf, Gio, Gst, Gtk

from .i18n import set_language
from .settings import load_settings
from .ui import MainWindow, install_css

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.png")


class ZdPlayerApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="com.zdplayer",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self) -> None:
        settings = load_settings()
        set_language(settings.language)

        install_css()

        if os.path.isfile(_LOGO_PATH):
            icons = []
            for size in (16, 24, 32, 48, 64, 128):
                icons.append(GdkPixbuf.Pixbuf.new_from_file_at_scale(_LOGO_PATH, size, size, True))
            Gtk.Window.set_default_icon_list(icons)

        window = self.props.active_window
        if window is None:
            window = MainWindow(self)

        if settings.start_maximized:
            window.maximize()

        window.present()


def main() -> int:
    Gst.init(None)
    app = ZdPlayerApplication()
    return app.run(None)
