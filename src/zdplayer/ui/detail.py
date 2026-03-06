from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from ..models import (
    CONTENT_LABELS,
    AccountProfile,
    CatalogEntry,
    SeriesEpisode,
    SeriesInfo,
    XtreamAccount,
)
from .helpers import clear_listbox, fill_placeholder, make_card, make_label


class DetailWidget(Gtk.Box):
    def __init__(
        self,
        *,
        on_action: Callable[[], None] | None = None,
        on_season_changed: Callable[[str], None] | None = None,
        on_episode_selected: Callable[[SeriesEpisode | None], None] | None = None,
        on_episode_activated: Callable[[SeriesEpisode], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._on_action = on_action
        self._on_season_changed = on_season_changed
        self._on_episode_selected = on_episode_selected
        self._on_episode_activated = on_episode_activated

        self._build_detail_card()
        self._build_series_panel()

    # ── Detail card ──

    def _build_detail_card(self) -> None:
        frame = make_card()
        box = frame.get_child()
        self.pack_start(frame, False, False, 0)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(hdr, False, False, 0)
        hdr.pack_start(make_label("Secili Icerik", css="card-title"), True, True, 0)
        self.kind_pill = make_label("Hazir", css="pill-count")
        hdr.pack_end(self.kind_pill, False, False, 0)

        self.title_label = make_label("Icerik secin", css="detail-title", wrap=True)
        self.meta_label = make_label("-", css="card-subtitle", wrap=True)
        self.summary_label = make_label(
            "Canli TV, film veya dizi secildiginde ayrintilar burada gorunur.",
            css="dim-text", wrap=True,
        )
        box.pack_start(self.title_label, False, False, 0)
        box.pack_start(self.meta_label, False, False, 0)
        box.pack_start(self.summary_label, False, False, 0)

        grid = Gtk.Grid(column_spacing=14, row_spacing=6)
        box.pack_start(grid, False, False, 0)
        self.val_account = self._kv(grid, 0, "Hesap")
        self.val_state = self._kv(grid, 1, "Durum")
        self.val_conn = self._kv(grid, 2, "Baglantilar")
        self.val_exp = self._kv(grid, 3, "Bitis")

        self.action_btn = Gtk.Button(label="Oynat")
        self.action_btn.get_style_context().add_class("action-btn")
        self.action_btn.connect("clicked", self._on_action_click)
        box.pack_start(self.action_btn, False, False, 0)

    @staticmethod
    def _kv(grid: Gtk.Grid, row: int, key: str) -> Gtk.Label:
        grid.attach(make_label(key, css="dim-text"), 0, row, 1, 1)
        val = make_label("-", css="detail-value", wrap=True)
        grid.attach(val, 1, row, 1, 1)
        return val

    # ── Series panel ──

    def _build_series_panel(self) -> None:
        self.series_rev = Gtk.Revealer()
        self.series_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.series_rev.set_transition_duration(220)
        self.pack_start(self.series_rev, False, False, 0)

        frame = make_card()
        self.series_rev.add(frame)
        box = frame.get_child()

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(hdr, False, False, 0)
        hdr.pack_start(make_label("Sezonlar ve Bolumler", css="card-title"), True, True, 0)
        self.series_pill = make_label("Sezon secin", css="pill-accent")
        hdr.pack_end(self.series_pill, False, False, 0)

        self.series_caption = make_label(
            "Secilen dizinin sezon ve bolumleri burada listelenir.",
            css="card-subtitle", wrap=True,
        )
        box.pack_start(self.series_caption, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.pack_start(make_label("Sezon", css="section-caption"), False, False, 0)
        self.season_combo = Gtk.ComboBoxText()
        self.season_combo.connect("changed", self._on_season)
        row.pack_start(self.season_combo, True, True, 0)
        box.pack_start(row, False, False, 0)

        self.ep_list = Gtk.ListBox()
        self.ep_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.ep_list.set_activate_on_single_click(False)
        self.ep_list.get_style_context().add_class("styled-list")
        self.ep_list.connect("row-selected", self._on_ep_sel)
        self.ep_list.connect("row-activated", self._on_ep_act)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(200)
        sw.add(self.ep_list)
        box.pack_start(sw, True, True, 0)

    # ── Internal events ──

    def _on_action_click(self, _btn: Gtk.Button) -> None:
        if self._on_action:
            self._on_action()

    def _on_season(self, combo: Gtk.ComboBoxText) -> None:
        key = combo.get_active_id()
        if key and self._on_season_changed:
            self._on_season_changed(key)

    def _on_ep_sel(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        ep = getattr(row, "episode", None)
        if self._on_episode_selected:
            self._on_episode_selected(ep)

    def _on_ep_act(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        ep = getattr(row, "episode", None)
        if ep and self._on_episode_activated:
            self._on_episode_activated(ep)

    # ── Public API ──

    def reset(
        self,
        *,
        account: XtreamAccount | None = None,
        profile: AccountProfile | None = None,
        state: str = "Hazir",
    ) -> None:
        self.kind_pill.set_text("Hazir")
        self.title_label.set_text("Icerik secin")
        self.meta_label.set_text("-")
        self.summary_label.set_text(
            "Canli TV, film veya dizi secildiginde ayrintilar burada gorunur."
        )
        self.action_btn.set_sensitive(False)
        self.val_account.set_text(account.name if account else "-")
        self.val_state.set_text(state)
        if profile:
            self.val_conn.set_text(profile.connections_label)
            self.val_exp.set_text(profile.expires_at or "-")
        else:
            self.val_conn.set_text("-")
            self.val_exp.set_text("-")

    def update_for_entry(
        self, entry: CatalogEntry, account: XtreamAccount | None, profile: AccountProfile | None,
    ) -> None:
        self.kind_pill.set_text(CONTENT_LABELS[entry.content_type])
        self.title_label.set_text(entry.name)
        self.meta_label.set_text(entry.meta_line or CONTENT_LABELS[entry.content_type])
        self.summary_label.set_text(entry.plot or entry.detail_summary)
        self.action_btn.set_sensitive(not entry.is_series_container)
        self.action_btn.set_label("Oynat" if not entry.is_series_container else "Bolum Sec")
        self.val_account.set_text(account.name if account else "-")
        self.val_state.set_text("Secili")
        if profile:
            self.val_conn.set_text(profile.connections_label)
            self.val_exp.set_text(profile.expires_at or "-")

    def update_for_episode(
        self, ep: SeriesEpisode, account: XtreamAccount | None, profile: AccountProfile | None,
    ) -> None:
        self.kind_pill.set_text("Bolum")
        self.title_label.set_text(ep.title)
        self.meta_label.set_text(ep.meta_line)
        self.summary_label.set_text(ep.plot or "Bolum aciklamasi yok.")
        self.action_btn.set_sensitive(True)
        self.action_btn.set_label("Bolumu Oynat")
        self.val_account.set_text(account.name if account else "-")
        self.val_state.set_text("Bolum secili")
        if profile:
            self.val_conn.set_text(profile.connections_label)
            self.val_exp.set_text(profile.expires_at or "-")

    def set_state_text(self, text: str) -> None:
        self.val_state.set_text(text)

    # ── Series public API ──

    def reset_series(self) -> None:
        self.series_rev.set_reveal_child(False)
        self.season_combo.remove_all()
        fill_placeholder(self.ep_list, "Bolum yok")

    def show_series_loading(self, name: str) -> None:
        self.series_rev.set_reveal_child(True)
        self.series_pill.set_text("Yukleniyor")
        self.series_caption.set_text(f"{name} sezon bilgileri cekiliyor...")
        self.season_combo.remove_all()
        self.season_combo.set_sensitive(False)
        fill_placeholder(self.ep_list, "Bolumler yukleniyor...")

    def show_series_error(self, message: str) -> None:
        self.series_rev.set_reveal_child(True)
        self.series_pill.set_text("Hata")
        self.series_caption.set_text(message)
        self.season_combo.remove_all()
        self.season_combo.set_sensitive(False)
        fill_placeholder(self.ep_list, "Bolumler yuklenemedi")

    def apply_series_info(self, info: SeriesInfo, entry: CatalogEntry) -> None:
        self.series_rev.set_reveal_child(True)
        self.series_pill.set_text(f"{len(info.seasons)} sezon")

        parts = [p for p in [info.genre, info.release_date, f"IMDB {info.rating}" if info.rating else None] if p]
        self.series_caption.set_text(" - ".join(parts) if parts else "Sezon secip bolum acabilirsiniz.")

        self.season_combo.remove_all()
        for s in info.seasons:
            label = s.name
            if s.episode_count:
                label = f"{label} ({s.episode_count} bolum)"
            self.season_combo.append(s.season_number, label)
        self.season_combo.set_sensitive(bool(info.seasons))

        if info.seasons:
            self.season_combo.set_active_id(info.seasons[0].season_number)

        self.kind_pill.set_text("Dizi")
        self.title_label.set_text(info.name)
        meta_parts = [p for p in [info.genre, info.release_date, f"IMDB {info.rating}" if info.rating else None] if p]
        self.meta_label.set_text(" - ".join(meta_parts) if meta_parts else "Dizi")
        self.summary_label.set_text(info.plot or entry.detail_summary)
        self.action_btn.set_sensitive(False)
        self.action_btn.set_label("Bolum Sec")

    def set_episodes(self, episodes: list[SeriesEpisode]) -> None:
        clear_listbox(self.ep_list)
        if not episodes:
            fill_placeholder(self.ep_list, "Bu sezonda bolum yok")
            return

        for ep in episodes:
            row = Gtk.ListBoxRow()
            row.episode = ep

            shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            shell.get_style_context().add_class("row-shell")
            shell.set_margin_top(4)
            shell.set_margin_bottom(4)
            shell.set_margin_start(8)
            shell.set_margin_end(8)

            num = make_label(str(ep.episode_number or "-"), css="num-pill", xalign=0.5)
            shell.pack_start(num, False, False, 0)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.pack_start(make_label(ep.title, css="ep-title", ellipsize=True), False, False, 0)
            text.pack_start(make_label(ep.meta_line, css="ep-subtitle", wrap=True), False, False, 0)
            shell.pack_start(text, True, True, 0)

            row.add(shell)
            self.ep_list.add(row)

        self.ep_list.show_all()
