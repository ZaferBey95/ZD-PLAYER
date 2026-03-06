from __future__ import annotations

from collections import Counter
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from ..models import CONTENT_LABELS, AccountProfile, CatalogEntry, MediaCategory, XtreamAccount
from .helpers import clear_listbox, fill_placeholder, make_card, make_label

CONTENT_TYPES = ("live", "movie", "series")


class SidebarWidget(Gtk.Box):
    def __init__(
        self,
        *,
        on_content_type_changed: Callable[[str], None] | None = None,
        on_category_selected: Callable[[str | None], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(310, -1)
        self._on_content_type_changed = on_content_type_changed
        self._on_category_selected = on_category_selected
        self._active_type = "live"
        self._selected_cat_ids: dict[str, str | None] = {k: None for k in CONTENT_TYPES}

        self._build_overview()
        self._build_switcher()
        self._build_categories()

    # ── Overview card ──

    def _build_overview(self) -> None:
        frame = make_card(css_extra="overview-card")
        box = frame.get_child()
        self.pack_start(frame, False, False, 0)

        box.pack_start(make_label("Hesap Ozeti", css="card-title"), False, False, 0)
        box.pack_start(make_label("Baglanti ve katalog durumu", css="card-subtitle"), False, False, 0)

        self.ov_account = make_label("Hesap secilmedi", css="metric-value", ellipsize=True)
        self.ov_server = make_label("-", css="dim-text", ellipsize=True)
        box.pack_start(self.ov_account, False, False, 0)
        box.pack_start(self.ov_server, False, False, 0)

        self.ov_status = make_label("Hazir", css="pill")
        self.ov_status.get_style_context().add_class("pill-warn")
        box.pack_start(self.ov_status, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        box.pack_start(grid, False, False, 0)
        self.ov_conn = self._add_kv(grid, 0, "Baglantilar")
        self.ov_exp = self._add_kv(grid, 1, "Bitis")
        self.ov_cat = self._add_kv(grid, 2, "Katalog")

    @staticmethod
    def _add_kv(grid: Gtk.Grid, row: int, key: str) -> Gtk.Label:
        grid.attach(make_label(key, css="overview-key"), 0, row, 1, 1)
        val = make_label("-", css="overview-value")
        grid.attach(val, 1, row, 1, 1)
        return val

    # ── Content type switcher ──

    def _build_switcher(self) -> None:
        frame = make_card()
        box = frame.get_child()
        self.pack_start(frame, False, False, 0)

        box.pack_start(make_label("Icerik", css="card-title"), False, False, 0)
        box.pack_start(
            make_label("Canli TV, filmler ve diziler", css="card-subtitle", wrap=True),
            False, False, 0,
        )

        sw = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(sw, False, False, 0)

        self._type_btns: dict[str, Gtk.Button] = {}
        for kind in CONTENT_TYPES:
            btn = Gtk.Button(label=CONTENT_LABELS[kind])
            btn.get_style_context().add_class("segment-btn")
            btn.connect("clicked", self._on_type_click, kind)
            sw.pack_start(btn, True, True, 0)
            self._type_btns[kind] = btn
        self._refresh_switcher()

    def _refresh_switcher(self) -> None:
        for kind, btn in self._type_btns.items():
            ctx = btn.get_style_context()
            ctx.remove_class("segment-btn-on")
            if kind == self._active_type:
                ctx.add_class("segment-btn-on")

    def _on_type_click(self, _btn: Gtk.Button, kind: str) -> None:
        if kind == self._active_type:
            return
        self._active_type = kind
        self._refresh_switcher()
        if self._on_content_type_changed:
            self._on_content_type_changed(kind)

    # ── Categories ──

    def _build_categories(self) -> None:
        frame = make_card(vexpand=True)
        box = frame.get_child()
        self.pack_start(frame, True, True, 0)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(hdr, False, False, 0)
        hdr.pack_start(make_label("Kategoriler", css="card-title"), True, True, 0)
        self.cat_count = make_label("0", css="pill-count")
        hdr.pack_end(self.cat_count, False, False, 0)

        box.pack_start(
            make_label("Secili icerik turune gore filtrelenir", css="section-caption"),
            False, False, 0,
        )

        self.cat_list = Gtk.ListBox()
        self.cat_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cat_list.get_style_context().add_class("styled-list")
        self.cat_list.get_style_context().add_class("category-list")
        self.cat_list.connect("row-selected", self._on_cat_selected)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.add(self.cat_list)
        box.pack_start(sw, True, True, 0)

    def _on_cat_selected(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        cid = getattr(row, "category_id", None)
        if cid is None:
            return
        self._selected_cat_ids[self._active_type] = cid
        if self._on_category_selected:
            self._on_category_selected(cid)

    # ── Public API ──

    @property
    def active_type(self) -> str:
        return self._active_type

    @active_type.setter
    def active_type(self, value: str) -> None:
        self._active_type = value
        self._refresh_switcher()

    def selected_category_id(self) -> str | None:
        return self._selected_cat_ids.get(self._active_type)

    def set_categories(
        self,
        categories: list[MediaCategory],
        entries: list[CatalogEntry],
    ) -> None:
        clear_listbox(self.cat_list)
        counts = Counter(e.category_id for e in entries)

        if not categories:
            self.cat_count.set_text("0")
            self._selected_cat_ids[self._active_type] = None
            fill_placeholder(self.cat_list, "Kategori yok")
            return

        sel = self._selected_cat_ids[self._active_type]
        ids = {c.id for c in categories}
        if sel not in ids:
            sel = categories[0].id
            self._selected_cat_ids[self._active_type] = sel

        for cat in categories:
            row = Gtk.ListBoxRow()
            row.category_id = cat.id

            shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            shell.get_style_context().add_class("row-shell")
            shell.set_margin_top(4)
            shell.set_margin_bottom(4)
            shell.set_margin_start(8)
            shell.set_margin_end(8)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.pack_start(make_label(cat.name, css="cat-title", ellipsize=True), False, False, 0)
            text.pack_start(
                make_label(CONTENT_LABELS[self._active_type], css="cat-subtitle"),
                False, False, 0,
            )
            shell.pack_start(text, True, True, 0)
            pill = make_label(str(counts.get(cat.id, 0)), css="pill-count")
            shell.pack_end(pill, False, False, 0)

            row.add(shell)
            self.cat_list.add(row)

        self.cat_count.set_text(str(len(categories)))
        self.cat_list.show_all()
        self._select_cat_row(sel)

    def _select_cat_row(self, cid: str | None) -> None:
        if not cid:
            return
        for row in self.cat_list.get_children():
            if getattr(row, "category_id", None) == cid:
                self.cat_list.select_row(row)
                return
        first = self.cat_list.get_row_at_index(0)
        if first:
            self.cat_list.select_row(first)

    def update_overview(
        self,
        account: XtreamAccount | None,
        profile: AccountProfile | None,
        *,
        item_count: int,
        status_override: str | None = None,
    ) -> None:
        if account is None:
            self.ov_account.set_text("Hesap secilmedi")
            self.ov_server.set_text("-")
            self.ov_conn.set_text("-")
            self.ov_exp.set_text("-")
            self.ov_cat.set_text("0 icerik")
            self._set_pill("Hazir")
            return

        self.ov_account.set_text(account.name)
        self.ov_server.set_text(f"{account.username} @ {account.host_label}")
        self.ov_cat.set_text(f"{item_count} icerik")

        if status_override:
            self.ov_conn.set_text("-")
            self.ov_exp.set_text("-")
            self._set_pill(status_override)
            return

        if profile is None:
            self.ov_conn.set_text("Baglaniyor")
            self.ov_exp.set_text("Yukleniyor")
            self._set_pill("Yukleniyor")
            return

        self.ov_conn.set_text(profile.connections_label)
        self.ov_exp.set_text(profile.expires_at or "-")
        self._set_pill(profile.status_label)

    def _set_pill(self, text: str) -> None:
        ctx = self.ov_status.get_style_context()
        for cls in ("pill-active", "pill-warn", "pill-danger"):
            ctx.remove_class(cls)
        low = text.lower()
        if "aktif" in low:
            ctx.add_class("pill-active")
        elif any(w in low for w in ("hata", "engelli", "doldu")):
            ctx.add_class("pill-danger")
        else:
            ctx.add_class("pill-warn")
        self.ov_status.set_text(text)
