from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk, Pango

from ..i18n import content_labels, t
from ..models import CatalogEntry, MediaCategory, SeriesEpisode, SeriesInfo

CONTENT_TYPES = ("live", "movie", "series")


class ChannelPanel(Gtk.Box):
    def __init__(
        self,
        *,
        on_content_type_changed: Callable[[str], None] | None = None,
        on_entry_activated: Callable[[CatalogEntry], None] | None = None,
        on_episode_activated: Callable[[SeriesEpisode], None] | None = None,
        on_series_selected: Callable[[CatalogEntry], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("panel")

        self._on_content_type_changed = on_content_type_changed
        self._on_entry_activated = on_entry_activated
        self._on_episode_activated = on_episode_activated
        self._on_series_selected = on_series_selected

        self._active_type = "live"
        self._entries: list[CatalogEntry] = []
        self._visible_entries: list[CatalogEntry] = []
        self._categories: list[MediaCategory] = []
        self._selected_cat_id: str | None = None
        self._search_timeout = 0

        self._browse_mode = "categories"
        self._visible_categories: list[MediaCategory] = []
        self._cat_entry_counts: dict[str, int] = {}
        self._all_row_visible = True

        self._series_mode = False
        self._series_info: SeriesInfo | None = None
        self._season_key: str | None = None
        self._visible_episodes: list[SeriesEpisode] = []

        self._build()

    @staticmethod
    def _adjacent_from_list(items: list[object], current_id: str, step: int) -> object | None:
        for idx, item in enumerate(items):
            if getattr(item, "id", None) != current_id:
                continue
            target_idx = idx + step
            if 0 <= target_idx < len(items):
                return items[target_idx]
            return None
        return None

    def _build(self) -> None:
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(180)
        self._stack.set_hhomogeneous(True)
        self._stack.set_vhomogeneous(True)

        # ── Catalog page ──
        catalog = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_margin_top(6)
        search_box.set_margin_start(6)
        search_box.set_margin_end(6)
        search_box.set_margin_bottom(4)
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(t("search"))
        self._search.get_style_context().add_class("dark-search")
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search)
        search_box.pack_start(self._search, True, True, 0)
        catalog.pack_start(search_box, False, False, 0)

        # Segmented tab control
        tab_outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_outer.get_style_context().add_class("tab-bar")
        tab_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_inner.get_style_context().add_class("tab-bar-inner")
        tab_inner.set_hexpand(True)
        self._tab_btns: dict[str, Gtk.Button] = {}
        labels = content_labels()
        for kind in CONTENT_TYPES:
            btn = Gtk.Button(label=labels[kind])
            btn.get_style_context().add_class("tab-btn")
            btn.set_hexpand(True)
            btn.connect("clicked", self._on_tab_click, kind)
            tab_inner.pack_start(btn, True, True, 0)
            self._tab_btns[kind] = btn
        tab_outer.pack_start(tab_inner, True, True, 0)
        catalog.pack_start(tab_outer, False, False, 0)
        self._refresh_tabs()

        # Nav bar (back button + title + badge) — hidden by default
        self._nav_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._nav_bar.get_style_context().add_class("nav-bar")
        self._nav_back_btn = Gtk.Button()
        self._nav_back_btn.get_style_context().add_class("nav-back-btn")
        back_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        back_icon = Gtk.Image.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.MENU)
        back_lbl = Gtk.Label(label=t("categories"))
        back_inner.pack_start(back_icon, False, False, 0)
        back_inner.pack_start(back_lbl, False, False, 0)
        self._nav_back_btn.add(back_inner)
        self._nav_back_btn.connect("clicked", self._on_cat_back)
        self._nav_bar.pack_start(self._nav_back_btn, False, False, 0)
        self._nav_title = Gtk.Label(label="")
        self._nav_title.get_style_context().add_class("nav-title")
        self._nav_title.set_ellipsize(Pango.EllipsizeMode.END)
        self._nav_title.set_xalign(0)
        self._nav_bar.pack_start(self._nav_title, True, True, 0)
        self._nav_badge = Gtk.Label(label="0")
        self._nav_badge.get_style_context().add_class("nav-badge")
        self._nav_bar.pack_start(self._nav_badge, False, False, 0)
        catalog.pack_start(self._nav_bar, False, False, 0)
        self._nav_bar.set_no_show_all(True)
        self._nav_bar.hide()

        # Info strip (category count, search results, etc.)
        self._info_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._info_strip.get_style_context().add_class("info-strip")
        self._info_text = Gtk.Label(label=t("categories_upper"))
        self._info_text.set_xalign(0)
        self._info_text.get_style_context().add_class("info-strip-text")
        self._info_strip.pack_start(self._info_text, True, True, 0)
        self._info_count = Gtk.Label(label="0")
        self._info_count.get_style_context().add_class("info-strip-text")
        self._info_strip.pack_start(self._info_count, False, False, 0)
        catalog.pack_start(self._info_strip, False, False, 0)

        # Browse stack: categories ListBox / entries TreeView
        self._browse_stack = Gtk.Stack()
        self._browse_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._browse_stack.set_transition_duration(150)
        self._browse_stack.set_hhomogeneous(True)
        self._browse_stack.set_vhomogeneous(True)

        sw_cat = Gtk.ScrolledWindow()
        sw_cat.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw_cat.set_vexpand(True)
        sw_cat.set_hexpand(True)
        sw_cat.set_overlay_scrolling(True)
        self._cat_listbox = Gtk.ListBox()
        self._cat_listbox.get_style_context().add_class("cat-listbox")
        self._cat_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._cat_listbox.set_hexpand(True)
        self._cat_listbox.connect("row-activated", self._on_cat_row_activated)
        sw_cat.add(self._cat_listbox)
        self._browse_stack.add_named(sw_cat, "categories")

        self._catalog_store = Gtk.ListStore(int, str, str)
        self._catalog_tree = self._make_tree(self._catalog_store)
        self._catalog_tree.connect("row-activated", self._on_catalog_activated)
        sw_entries = Gtk.ScrolledWindow()
        sw_entries.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw_entries.set_vexpand(True)
        sw_entries.set_hexpand(True)
        sw_entries.set_overlay_scrolling(True)
        sw_entries.add(self._catalog_tree)
        self._browse_stack.add_named(sw_entries, "entries")

        catalog.pack_start(self._browse_stack, True, True, 0)
        self._stack.add_named(catalog, "catalog")

        # ── Series page ──
        series = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        series_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        series_nav.get_style_context().add_class("nav-bar")
        series_back = Gtk.Button()
        series_back.get_style_context().add_class("nav-back-btn")
        sb_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        sb_icon = Gtk.Image.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.MENU)
        sb_lbl = Gtk.Label(label=t("back"))
        sb_inner.pack_start(sb_icon, False, False, 0)
        sb_inner.pack_start(sb_lbl, False, False, 0)
        series_back.add(sb_inner)
        series_back.connect("clicked", self._on_series_back)
        series_nav.pack_start(series_back, False, False, 0)
        self._series_name_label = Gtk.Label(label="")
        self._series_name_label.get_style_context().add_class("nav-title")
        self._series_name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._series_name_label.set_xalign(0)
        series_nav.pack_start(self._series_name_label, True, True, 0)
        series.pack_start(series_nav, False, False, 0)

        self._series_meta_label = Gtk.Label(label="")
        self._series_meta_label.get_style_context().add_class("series-meta")
        self._series_meta_label.set_margin_start(8)
        self._series_meta_label.set_margin_top(4)
        self._series_meta_label.set_xalign(0)
        self._series_meta_label.set_ellipsize(Pango.EllipsizeMode.END)
        series.pack_start(self._series_meta_label, False, False, 0)

        season_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        season_bar.get_style_context().add_class("cat-bar")
        self._season_combo = Gtk.ComboBoxText()
        self._season_combo.set_hexpand(True)
        self._season_combo.connect("changed", self._on_season_changed)
        season_bar.pack_start(self._season_combo, True, True, 0)
        series.pack_start(season_bar, False, False, 0)

        self._episode_store = Gtk.ListStore(int, str, str)
        self._episode_tree = self._make_tree(self._episode_store, name_header=t("episode"))
        self._episode_tree.connect("row-activated", self._on_episode_row_activated)
        sw2 = Gtk.ScrolledWindow()
        sw2.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw2.set_vexpand(True)
        sw2.add(self._episode_tree)
        series.pack_start(sw2, True, True, 0)

        self._stack.add_named(series, "series")
        self.pack_start(self._stack, True, True, 0)
        self._stack.set_visible_child_name("catalog")

    # ── Category row builder ──

    def _make_cat_row(self, name: str, count: int) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class("cat-row-box")

        lbl_name = Gtk.Label(label=name)
        lbl_name.get_style_context().add_class("cat-row-name")
        lbl_name.set_xalign(0)
        lbl_name.set_ellipsize(Pango.EllipsizeMode.END)
        lbl_name.set_hexpand(True)
        box.pack_start(lbl_name, True, True, 0)

        lbl_count = Gtk.Label(label=str(count))
        lbl_count.get_style_context().add_class("cat-row-count")
        box.pack_start(lbl_count, False, False, 0)

        lbl_arrow = Gtk.Label(label="\u203a")
        lbl_arrow.get_style_context().add_class("cat-row-arrow")
        box.pack_start(lbl_arrow, False, False, 0)

        row.add(box)
        return row

    def _make_tree(
        self, store: Gtk.ListStore, *, name_header: str | None = None
    ) -> Gtk.TreeView:
        if name_header is None:
            name_header = t("channel")
        tree = Gtk.TreeView(model=store)
        tree.set_headers_visible(True)
        tree.set_enable_search(False)
        tree.set_activate_on_single_click(False)
        tree.get_style_context().add_class("channel-list")
        tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        renderer_num = Gtk.CellRendererText()
        renderer_num.set_property("xalign", 1.0)
        renderer_num.set_property("xpad", 8)
        renderer_num.set_property("ypad", 6)
        col_num = Gtk.TreeViewColumn("#", renderer_num, text=1)
        col_num.set_fixed_width(50)
        col_num.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        tree.append_column(col_num)

        renderer_name = Gtk.CellRendererText()
        renderer_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        renderer_name.set_property("xpad", 8)
        renderer_name.set_property("ypad", 6)
        col_name = Gtk.TreeViewColumn(name_header, renderer_name, text=2)
        col_name.set_expand(True)
        tree.append_column(col_name)

        return tree

    # ── Tabs ──

    def _refresh_tabs(self) -> None:
        for kind, btn in self._tab_btns.items():
            ctx = btn.get_style_context()
            ctx.remove_class("tab-btn-active")
            if kind == self._active_type:
                ctx.add_class("tab-btn-active")

    def _on_tab_click(self, _btn: Gtk.Button, kind: str) -> None:
        if kind == self._active_type and not self._series_mode:
            return
        self._active_type = kind
        self._series_mode = False
        self._browse_mode = "categories"
        self._selected_cat_id = None
        self._stack.set_visible_child_name("catalog")
        self._refresh_tabs()
        self._search.set_text("")
        if self._on_content_type_changed:
            self._on_content_type_changed(kind)

    # ── Nav helpers ──

    def _show_nav(self, title: str, count: int) -> None:
        self._nav_title.set_text(title)
        self._nav_badge.set_text(str(count))
        self._nav_bar.set_no_show_all(False)
        self._nav_bar.show_all()
        self._info_strip.hide()

    def _hide_nav(self) -> None:
        self._nav_bar.hide()
        self._nav_bar.set_no_show_all(True)
        self._info_strip.show()

    def _on_cat_back(self, _btn: Gtk.Button) -> None:
        self._browse_mode = "categories"
        self._selected_cat_id = None
        self._search.set_text("")
        self._show_categories()

    # ── Search ──

    def _on_search(self, _entry: Gtk.SearchEntry) -> None:
        if self._search_timeout:
            GLib.source_remove(self._search_timeout)
        self._search_timeout = GLib.timeout_add(150, self._apply_search)

    def _apply_search(self) -> bool:
        self._search_timeout = 0
        query = self._search.get_text().strip().lower()
        if self._browse_mode == "categories":
            if query:
                self._show_filtered_categories(query)
            else:
                self._show_categories()
        else:
            self._rebuild_entry_list()
        return False

    # ── Category list ──

    def _compute_counts(self) -> None:
        self._cat_entry_counts = {}
        for e in self._entries:
            cid = e.category_id
            if cid:
                self._cat_entry_counts[cid] = self._cat_entry_counts.get(cid, 0) + 1

    def _show_categories(self) -> None:
        self._browse_mode = "categories"
        self._hide_nav()
        self._info_text.set_text(t("categories_upper"))

        for child in self._cat_listbox.get_children():
            self._cat_listbox.remove(child)

        self._visible_categories = []
        self._all_row_visible = True

        row_all = self._make_cat_row(t("all"), len(self._entries))
        self._cat_listbox.add(row_all)

        for cat in self._categories:
            count = self._cat_entry_counts.get(cat.id, 0)
            row = self._make_cat_row(cat.name, count)
            self._cat_listbox.add(row)
            self._visible_categories.append(cat)

        self._cat_listbox.show_all()
        self._info_count.set_text(str(len(self._visible_categories) + 1))
        self._browse_stack.set_visible_child_name("categories")

    def _show_filtered_categories(self, query: str) -> None:
        self._hide_nav()
        self._info_text.set_text(t("categories_upper"))

        for child in self._cat_listbox.get_children():
            self._cat_listbox.remove(child)

        self._visible_categories = []

        # "All" row — show if query matches
        all_label = t("all").lower()
        self._all_row_visible = query in all_label
        if self._all_row_visible:
            row_all = self._make_cat_row(t("all"), len(self._entries))
            self._cat_listbox.add(row_all)

        for cat in self._categories:
            if query not in cat.name.lower():
                continue
            count = self._cat_entry_counts.get(cat.id, 0)
            row = self._make_cat_row(cat.name, count)
            self._cat_listbox.add(row)
            self._visible_categories.append(cat)

        self._cat_listbox.show_all()
        shown = len(self._visible_categories) + (1 if query in all_label else 0)
        self._info_count.set_text(str(shown))
        self._browse_stack.set_visible_child_name("categories")

    # ── Category row activated ──

    def _on_cat_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if self._all_row_visible:
            if idx == 0:
                self._enter_category(None, t("all"))
                return
            cat_idx = idx - 1
        else:
            cat_idx = idx
        if 0 <= cat_idx < len(self._visible_categories):
            cat = self._visible_categories[cat_idx]
            self._enter_category(cat.id, cat.name)

    # ── Entry list ──

    def _enter_category(self, cat_id: str | None, cat_name: str) -> None:
        self._browse_mode = "entries"
        self._selected_cat_id = cat_id
        self._search.set_text("")
        self._rebuild_entry_list()
        self._show_nav(cat_name, len(self._visible_entries))
        self._browse_stack.set_visible_child_name("entries")

    def _rebuild_entry_list(self) -> None:
        self._catalog_store.clear()
        query = self._search.get_text().strip().lower()
        cat_id = self._selected_cat_id

        self._visible_entries = []
        for entry in self._entries:
            if cat_id and entry.category_id != cat_id:
                continue
            if query and query not in entry.search_blob:
                continue
            idx = len(self._visible_entries)
            self._catalog_store.append([idx, str(idx + 1), entry.name])
            self._visible_entries.append(entry)

        if self._browse_mode == "entries":
            self._nav_badge.set_text(str(len(self._visible_entries)))

    def _on_catalog_activated(
        self, tree: Gtk.TreeView, path: Gtk.TreePath, _col: Gtk.TreeViewColumn,
    ) -> None:
        model = tree.get_model()
        it = model.get_iter(path)
        if it is None:
            return
        idx = model.get_value(it, 0)

        if idx < 0 or idx >= len(self._visible_entries):
            return
        entry = self._visible_entries[idx]

        if entry.content_type == "series":
            if self._on_series_selected:
                self._on_series_selected(entry)
        else:
            if self._on_entry_activated:
                self._on_entry_activated(entry)

    # ── Series mode ──

    def enter_series(self, info: SeriesInfo) -> None:
        self._series_mode = True
        self._series_info = info
        self._series_name_label.set_text(info.name)

        parts = [p for p in [info.genre, info.release_date,
                 f"IMDB {info.rating}" if info.rating else None] if p]
        self._series_meta_label.set_text(" - ".join(parts) if parts else "")

        self._season_combo.remove_all()
        for s in info.seasons:
            label = s.name
            if s.episode_count:
                label += f" ({t('episodes_count', count=s.episode_count)})"
            self._season_combo.append(s.season_number, label)

        if info.seasons:
            self._season_combo.set_active_id(info.seasons[0].season_number)
            self._season_key = info.seasons[0].season_number
            self._fill_episodes(info.seasons[0].season_number)

        self._stack.set_visible_child_name("series")

    def show_series_loading(self, name: str) -> None:
        self._series_mode = True
        self._series_name_label.set_text(name)
        self._series_meta_label.set_text(t("loading"))
        self._season_combo.remove_all()
        self._episode_store.clear()
        self._visible_episodes = []
        self._stack.set_visible_child_name("series")

    def show_series_error(self, msg: str) -> None:
        self._series_meta_label.set_text(msg)

    def _fill_episodes(self, season_key: str) -> None:
        self._episode_store.clear()
        self._visible_episodes = []
        if not self._series_info:
            return
        episodes = self._series_info.episodes_by_season.get(season_key, [])
        for ep in episodes:
            idx = len(self._visible_episodes)
            num = str(ep.episode_number) if ep.episode_number is not None else str(idx + 1)
            self._episode_store.append([idx, num, ep.title])
            self._visible_episodes.append(ep)

    def _on_season_changed(self, combo: Gtk.ComboBoxText) -> None:
        key = combo.get_active_id()
        if key:
            self._season_key = key
            self._fill_episodes(key)

    def _on_episode_row_activated(
        self, tree: Gtk.TreeView, path: Gtk.TreePath, _col: Gtk.TreeViewColumn,
    ) -> None:
        model = tree.get_model()
        it = model.get_iter(path)
        if it is None:
            return
        idx = model.get_value(it, 0)
        if idx < 0 or idx >= len(self._visible_episodes):
            return
        ep = self._visible_episodes[idx]
        if self._on_episode_activated:
            self._on_episode_activated(ep)

    def _on_series_back(self, _btn: Gtk.Button) -> None:
        self._series_mode = False
        self._series_info = None
        self._stack.set_visible_child_name("catalog")

    # ── Public API ──

    @property
    def active_type(self) -> str:
        return self._active_type

    def set_catalog(
        self,
        categories: list[MediaCategory],
        entries: list[CatalogEntry],
    ) -> None:
        self._categories = categories
        self._entries = entries
        self._selected_cat_id = None
        self._compute_counts()
        self._show_categories()

    def set_loading(self) -> None:
        self._catalog_store.clear()
        self._visible_entries = []
        self._visible_categories = []
        for child in self._cat_listbox.get_children():
            self._cat_listbox.remove(child)
        self._hide_nav()
        self._info_text.set_text(t("loading_upper"))
        self._info_count.set_text("...")
        self._browse_stack.set_visible_child_name("categories")

    def clear_search(self) -> None:
        self._search.set_text("")

    def switch_tab(self, kind: str) -> None:
        if kind in CONTENT_TYPES:
            self._active_type = kind
            self._refresh_tabs()

    def select_episode(self, episode_id: str) -> SeriesEpisode | None:
        if not self._series_info:
            return None

        episode = self._series_info.find_episode(episode_id)
        if episode is None:
            return None

        if self._season_combo.get_active_id() != episode.season_number:
            self._season_combo.set_active_id(episode.season_number)
        else:
            self._fill_episodes(episode.season_number)

        for idx, current in enumerate(self._visible_episodes):
            if current.id != episode_id:
                continue
            path = Gtk.TreePath.new_from_string(str(idx))
            selection = self._episode_tree.get_selection()
            selection.unselect_all()
            selection.select_path(path)
            self._episode_tree.scroll_to_cell(path, None, False, 0.0, 0.0)
            break

        return episode

    def select_entry(self, entry_id: str) -> CatalogEntry | None:
        for idx, current in enumerate(self._visible_entries):
            if current.id != entry_id:
                continue
            path = Gtk.TreePath.new_from_string(str(idx))
            selection = self._catalog_tree.get_selection()
            selection.unselect_all()
            selection.select_path(path)
            self._catalog_tree.scroll_to_cell(path, None, False, 0.0, 0.0)
            return current
        return None

    def adjacent_entry(self, entry_id: str, step: int) -> CatalogEntry | None:
        item = self._adjacent_from_list(self._visible_entries, entry_id, step)
        return item if isinstance(item, CatalogEntry) else None

    def adjacent_episode(self, episode_id: str, step: int) -> SeriesEpisode | None:
        if not self._series_info:
            return None
        item = self._adjacent_from_list(self._visible_episodes, episode_id, step)
        return item if isinstance(item, SeriesEpisode) else None
