from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk

from ..models import CONTENT_LABELS, CatalogEntry
from .helpers import clear_listbox, fill_placeholder, make_label


class BrowserWidget(Gtk.Box):
    def __init__(
        self,
        *,
        on_entry_selected: Callable[[CatalogEntry | None], None] | None = None,
        on_entry_activated: Callable[[CatalogEntry], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._on_entry_selected = on_entry_selected
        self._on_entry_activated = on_entry_activated
        self._all_entries: list[CatalogEntry] = []
        self._category_id: str | None = None
        self._search_timeout = 0

        self._build()

    def _build(self) -> None:
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.pack_start(hdr, False, False, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.title_label = make_label("Canli TV", css="card-title")
        self.hint_label = make_label("Kategoriden secin, listeden acin", css="card-subtitle")
        left.pack_start(self.title_label, False, False, 0)
        left.pack_start(self.hint_label, False, False, 0)
        hdr.pack_start(left, True, True, 0)

        self.count_label = make_label("0 / 0", css="pill-count")
        hdr.pack_end(self.count_label, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Listede ara...")
        self.search.get_style_context().add_class("search-box")
        self.search.connect("search-changed", self._on_search)
        self.pack_start(self.search, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.get_style_context().add_class("styled-list")
        self.listbox.connect("row-selected", self._on_selected)
        self.listbox.connect("row-activated", self._on_activated)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.add(self.listbox)
        self.pack_start(sw, True, True, 0)

    # ── Events ──

    def _on_search(self, _entry: Gtk.SearchEntry) -> None:
        if self._search_timeout:
            GLib.source_remove(self._search_timeout)
        self._search_timeout = GLib.timeout_add(140, self._apply_search)

    def _apply_search(self) -> bool:
        self._search_timeout = 0
        self.refresh()
        return False

    def _on_selected(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        entry = getattr(row, "entry", None)
        if self._on_entry_selected:
            self._on_entry_selected(entry)

    def _on_activated(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        entry = getattr(row, "entry", None)
        if entry and self._on_entry_activated:
            self._on_entry_activated(entry)

    # ── Public API ──

    def set_content_type(self, content_type: str) -> None:
        hints = {
            "live": "Kanali secin, oynatmak icin cift tiklayin",
            "movie": "Filmi secin, oynatmak icin cift tiklayin",
            "series": "Diziyi secin, sezon ve bolumleri acin",
        }
        self.title_label.set_text(CONTENT_LABELS.get(content_type, content_type))
        self.hint_label.set_text(hints.get(content_type, ""))

    def set_entries(
        self,
        entries: list[CatalogEntry],
        category_id: str | None = None,
    ) -> None:
        self._all_entries = entries
        self._category_id = category_id
        self.refresh()

    def set_category(self, category_id: str | None) -> None:
        self._category_id = category_id
        self.refresh()

    def clear_search(self) -> None:
        self.search.set_text("")

    def refresh(self) -> None:
        clear_listbox(self.listbox)
        query = self.search.get_text().strip().lower()
        cid = self._category_id

        filtered: list[CatalogEntry] = []
        for e in self._all_entries:
            if cid and e.category_id != cid:
                continue
            if query and query not in e.search_blob:
                continue
            filtered.append(e)

        total = len(self._all_entries)
        self.count_label.set_text(f"{len(filtered)} / {total}")

        if not filtered:
            fill_placeholder(self.listbox, "Eslesen icerik yok")
            return

        for entry in filtered:
            row = Gtk.ListBoxRow()
            row.entry = entry

            shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            shell.get_style_context().add_class("row-shell")
            shell.set_margin_top(4)
            shell.set_margin_bottom(4)
            shell.set_margin_start(8)
            shell.set_margin_end(8)

            lead = self._make_lead(entry)
            shell.pack_start(lead, False, False, 0)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.pack_start(make_label(entry.name, css="entry-title", ellipsize=True), False, False, 0)
            text.pack_start(
                make_label(entry.meta_line or entry.detail_summary, css="entry-subtitle", wrap=True),
                False, False, 0,
            )
            shell.pack_start(text, True, True, 0)

            badge = make_label(CONTENT_LABELS[entry.content_type], css="type-pill")
            badge.get_style_context().add_class(
                {"live": "type-live", "movie": "type-movie", "series": "type-series"}[entry.content_type]
            )
            shell.pack_end(badge, False, False, 0)

            row.add(shell)
            self.listbox.add(row)

        self.listbox.show_all()

    @staticmethod
    def _make_lead(entry: CatalogEntry) -> Gtk.Label:
        if entry.content_type == "live":
            txt = str(entry.number) if entry.number is not None else "LIVE"
        elif entry.content_type == "movie":
            txt = "FILM"
        else:
            txt = "DIZI"
        lbl = make_label(txt, css="num-pill", xalign=0.5)
        return lbl

    def set_loading(self) -> None:
        clear_listbox(self.listbox)
        fill_placeholder(self.listbox, "Icerikler yukleniyor...")
        self.count_label.set_text("0 / 0")
