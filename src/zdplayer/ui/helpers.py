from __future__ import annotations

from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Pango


def clear_listbox(listbox: Gtk.ListBox) -> None:
    for child in listbox.get_children():
        listbox.remove(child)


def host_label(server: str) -> str:
    value = server.strip()
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    return parsed.netloc or parsed.path or server


def suggest_account_name(server: str, username: str) -> str:
    host = host_label(server)
    return f"{username}@{host}" if username else host


def make_label(
    text: str,
    *,
    css: str | None = None,
    xalign: float = 0.0,
    ellipsize: bool = False,
    wrap: bool = False,
    max_chars: int = 60,
) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=xalign)
    if css:
        label.get_style_context().add_class(css)
    if ellipsize:
        label.set_ellipsize(Pango.EllipsizeMode.END)
    if wrap:
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(max_chars)
    return label


def make_icon_button(
    icon_name: str,
    tooltip: str,
    *,
    css: str | None = None,
    size: int = Gtk.IconSize.BUTTON,
) -> Gtk.Button:
    button = Gtk.Button.new_from_icon_name(icon_name, size)
    button.set_tooltip_text(tooltip)
    if css:
        button.get_style_context().add_class(css)
    return button


def fill_placeholder(listbox: Gtk.ListBox, text: str) -> None:
    clear_listbox(listbox)
    row = Gtk.ListBoxRow(selectable=False, activatable=False)
    label = make_label(text, css="dim-text", wrap=True)
    label.set_margin_top(24)
    label.set_margin_bottom(24)
    label.set_margin_start(16)
    label.set_margin_end(16)
    row.add(label)
    listbox.add(row)
    listbox.show_all()


def make_card(*, vexpand: bool = False, css_extra: str | None = None) -> Gtk.Frame:
    frame = Gtk.Frame()
    frame.set_shadow_type(Gtk.ShadowType.NONE)
    frame.set_vexpand(vexpand)
    frame.get_style_context().add_class("card")
    if css_extra:
        frame.get_style_context().add_class(css_extra)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_border_width(16)
    frame.add(box)
    return frame
