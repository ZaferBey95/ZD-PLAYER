from __future__ import annotations

import os
import threading

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")

from gi.repository import GdkPixbuf, GLib, Gtk, Pango

from ..i18n import content_labels, t
from ..models import (
    AccountProfile,
    CatalogEntry,
    MediaCategory,
    SeriesEpisode,
    SeriesInfo,
    XtreamAccount,
)
from ..m3u import M3UError, fetch_and_parse as m3u_fetch
from ..settings import get_settings, save_settings
from ..storage import AccountStore, StorageError
from ..xtream import XtreamClient, XtreamError
from .channel_panel import ChannelPanel
from .dialogs import ManageAccountsDialog
from .helpers import make_icon_button, make_label
from .player import PlayerWidget
from .settings_dialog import SettingsDialog

CONTENT_TYPES = ("live", "movie", "series")

_LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo.png")


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application)
        self.set_title(t("app_name"))
        self.set_default_size(1400, 820)

        self.store = AccountStore()
        self.client = XtreamClient()

        self.accounts: list[XtreamAccount] = []
        self.active_account_id: str | None = None
        self.current_profile: AccountProfile | None = None

        self.categories_by_type: dict[str, list[MediaCategory]] = {k: [] for k in CONTENT_TYPES}
        self.entries_by_type: dict[str, list[CatalogEntry]] = {k: [] for k in CONTENT_TYPES}
        self.catalog_loaded: dict[str, bool] = {k: False for k in CONTENT_TYPES}

        self.series_info_cache: dict[str, SeriesInfo] = {}
        self.catalog_token = 0
        self.series_token = 0
        self.ignore_combo = False
        self._autoplay_done = False

        self._build_ui()
        self._load_saved_accounts()
        self.show_all()
        self.connect("destroy", self._on_destroy)

    # ── UI ──

    def _build_ui(self) -> None:
        self._build_headerbar()

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        # Left: player
        self.player = PlayerWidget(
            on_error=self._on_player_error,
            on_eos=self._on_player_eos,
        )
        self.player.empty_btn.connect("clicked", self._on_manage_clicked)
        paned.pack1(self.player, resize=True, shrink=False)

        # Right: channel panel
        self.panel = ChannelPanel(
            on_content_type_changed=self._on_content_type_changed,
            on_entry_activated=self._on_entry_activated,
            on_episode_activated=self._on_episode_activated,
            on_series_selected=self._on_series_selected,
        )
        self.panel.set_size_request(340, -1)
        paned.pack2(self.panel, resize=False, shrink=False)

        # Set divider position (window width - panel width)
        self.connect("size-allocate", self._on_size_allocate_once)
        self._paned = paned
        self._paned_initialized = False

    def _build_headerbar(self) -> None:
        hbar = Gtk.HeaderBar()
        hbar.set_show_close_button(True)
        self.set_titlebar(hbar)

        # Left: logo + now playing info
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_box.set_valign(Gtk.Align.CENTER)
        if os.path.isfile(_LOGO_PATH):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(_LOGO_PATH, 28, 28, True)
            logo_img = Gtk.Image.new_from_pixbuf(pixbuf)
            title_box.pack_start(logo_img, False, False, 0)

        np_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        np_box.set_valign(Gtk.Align.CENTER)
        self._np_title = Gtk.Label(label=t("app_name"))
        self._np_title.get_style_context().add_class("now-playing")
        self._np_title.set_xalign(0)
        self._np_title.set_ellipsize(Pango.EllipsizeMode.END)
        self._np_title.set_max_width_chars(50)
        self._np_meta = Gtk.Label(label=t("app_subtitle"))
        self._np_meta.get_style_context().add_class("now-meta")
        self._np_meta.set_xalign(0)
        self._np_meta.set_ellipsize(Pango.EllipsizeMode.END)
        np_box.pack_start(self._np_title, False, False, 0)
        np_box.pack_start(self._np_meta, False, False, 0)
        title_box.pack_start(np_box, False, False, 0)
        hbar.set_custom_title(title_box)

        # Right: controls
        self.spinner = Gtk.Spinner()
        self.spinner.set_no_show_all(True)
        hbar.pack_end(self.spinner)

        self.settings_btn = make_icon_button("emblem-system-symbolic", t("settings"))
        self.settings_btn.connect("clicked", self._on_settings_clicked)
        hbar.pack_end(self.settings_btn)

        self.refresh_btn = make_icon_button("view-refresh-symbolic", t("refresh"))
        self.refresh_btn.connect("clicked", self._on_refresh)
        hbar.pack_end(self.refresh_btn)

        self.manage_btn = make_icon_button("system-users-symbolic", t("accounts"))
        self.manage_btn.connect("clicked", self._on_manage_clicked)
        hbar.pack_end(self.manage_btn)

        self.account_combo = Gtk.ComboBoxText()
        self.account_combo.set_size_request(200, -1)
        self.account_combo.set_tooltip_text(t("active_account"))
        self.account_combo.connect("changed", self._on_account_changed)
        hbar.pack_end(self.account_combo)

    # ── Now-playing header ──

    def _on_size_allocate_once(self, widget: Gtk.Widget, alloc: object) -> None:
        if not self._paned_initialized:
            w = self.get_allocated_width()
            if w > 400:
                self._paned.set_position(w - 340)
                self._paned_initialized = True

    def _update_np(self, title: str | None = None, meta: str | None = None) -> None:
        self._np_title.set_text(title or t("app_name"))
        self._np_meta.set_text(meta or t("app_subtitle"))

    # ── Account management ──

    def _load_saved_accounts(self) -> None:
        try:
            accounts, last_id = self.store.load()
        except StorageError as exc:
            accounts, last_id = [], None
            self._show_error(str(exc))

        self.accounts = accounts
        ids = {a.id for a in accounts}
        if last_id in ids:
            self.active_account_id = last_id
        elif accounts:
            self.active_account_id = accounts[0].id
        else:
            self.active_account_id = None

        # Switch to last channel's content type tab if needed
        settings = get_settings()
        if (settings.remember_last_channel
                and settings.last_channel_type
                and settings.last_channel_type in CONTENT_TYPES
                and settings.last_channel_type != "live"):
            self.panel.switch_tab(settings.last_channel_type)

        self._rebuild_combo()
        if not self.active_account_id:
            self._handle_no_accounts()

    def _rebuild_combo(self) -> None:
        self.ignore_combo = True
        self.account_combo.remove_all()
        for a in self.accounts:
            self.account_combo.append(a.id, a.name)
        has = bool(self.accounts)
        self.account_combo.set_sensitive(has)
        self.refresh_btn.set_sensitive(has)
        if has and self.active_account_id:
            self.account_combo.set_active_id(self.active_account_id)
        self.ignore_combo = False
        if has and self.active_account_id:
            self._load_catalog()

    def _persist(self) -> None:
        try:
            self.store.save(self.accounts, self.active_account_id)
        except StorageError as exc:
            self._show_error(str(exc))

    def _active_account(self) -> XtreamAccount | None:
        for a in self.accounts:
            if a.id == self.active_account_id:
                return a
        return None

    def _handle_no_accounts(self) -> None:
        self._invalidate_cache()
        self._set_loading(False)
        self.refresh_btn.set_sensitive(False)
        self.account_combo.set_sensitive(False)
        self.panel.set_loading()
        self.player.show_empty(t("add_account"), t("add_account_sub"), show_btn=True)
        self._update_np()

    def _invalidate_cache(self) -> None:
        self.categories_by_type = {k: [] for k in CONTENT_TYPES}
        self.entries_by_type = {k: [] for k in CONTENT_TYPES}
        self.catalog_loaded = {k: False for k in CONTENT_TYPES}
        self.series_info_cache.clear()

    # ── Catalog loading ──

    def _set_loading(self, on: bool) -> None:
        if on:
            self.spinner.show()
            self.spinner.start()
        else:
            self.spinner.stop()
            self.spinner.hide()

    def _load_catalog(self, *, force: bool = False) -> None:
        account = self._active_account()
        if not account:
            self._handle_no_accounts()
            return
        ct = self.panel.active_type
        if self.catalog_loaded[ct] and not force:
            self._apply_views()
            return

        self.catalog_token += 1
        token = self.catalog_token
        self._set_loading(True)
        self.panel.set_loading()
        labels = content_labels()
        self._update_np(t("loading"), t("catalog_loading", content=labels[ct]))

        thread = threading.Thread(
            target=self._catalog_worker, args=(token, account, ct), daemon=True,
        )
        thread.start()

    def _catalog_worker(self, token: int, account: XtreamAccount, ct: str) -> None:
        if account.account_type == "m3u":
            self._m3u_worker(token, account, ct)
            return
        try:
            profile, cats, entries = self.client.fetch_catalog(account, ct)
        except XtreamError as exc:
            GLib.idle_add(self._catalog_error, token, account.id, ct, str(exc))
            return
        GLib.idle_add(self._catalog_done, token, account.id, ct, profile, cats, entries)

    def _m3u_worker(self, token: int, account: XtreamAccount, ct: str) -> None:
        if ct != "live":
            profile = AccountProfile(account_status="Active")
            GLib.idle_add(self._catalog_done, token, account.id, ct, profile, [], [])
            return
        try:
            cats, entries = m3u_fetch(account.m3u_url)
        except M3UError as exc:
            GLib.idle_add(self._catalog_error, token, account.id, ct, str(exc))
            return
        profile = AccountProfile(account_status="Active")
        GLib.idle_add(self._catalog_done, token, account.id, ct, profile, cats, entries)

    def _catalog_done(
        self, token: int, aid: str, ct: str,
        profile: AccountProfile, cats: list[MediaCategory], entries: list[CatalogEntry],
    ) -> bool:
        if aid != self.active_account_id:
            return False
        self.current_profile = profile
        self.categories_by_type[ct] = cats
        self.entries_by_type[ct] = entries
        self.catalog_loaded[ct] = True
        if token != self.catalog_token or ct != self.panel.active_type:
            return False
        self._set_loading(False)
        self._apply_views()
        self._try_autoplay(ct, entries)
        return False

    def _try_autoplay(self, ct: str, entries: list[CatalogEntry]) -> None:
        if self._autoplay_done:
            return
        self._autoplay_done = True
        settings = get_settings()
        if not settings.remember_last_channel:
            return
        if not settings.last_channel_id or not settings.last_account_id:
            return
        if settings.last_account_id != self.active_account_id:
            return
        if settings.last_channel_type != ct:
            return
        for entry in entries:
            if entry.id == settings.last_channel_id:
                self._play_entry(entry)
                return

    def _catalog_error(self, token: int, aid: str, ct: str, msg: str) -> bool:
        if token != self.catalog_token or aid != self.active_account_id:
            return False
        self._set_loading(False)
        self.catalog_loaded[ct] = False
        self.panel.set_loading()
        self.player.show_empty(t("connection_error"), msg)
        self._update_np(t("error"), msg)
        self._show_error(msg)
        return False

    def _apply_views(self) -> None:
        ct = self.panel.active_type
        account = self._active_account()
        cats = self.categories_by_type[ct]
        entries = self.entries_by_type[ct]
        self.panel.set_catalog(cats, entries)

        labels = content_labels()
        if account:
            self._update_np(account.name, labels[ct])

    # ── Series loading ──

    def _load_series(self, entry: CatalogEntry) -> None:
        if entry.id in self.series_info_cache:
            self.panel.enter_series(self.series_info_cache[entry.id])
            return
        account = self._active_account()
        if not account:
            return
        self.series_token += 1
        token = self.series_token
        self.panel.show_series_loading(entry.name)
        thread = threading.Thread(
            target=self._series_worker, args=(token, account, entry.id, entry.name), daemon=True,
        )
        thread.start()

    def _series_worker(self, token: int, account: XtreamAccount, sid: str, name: str) -> None:
        try:
            info = self.client.fetch_series_info(account, sid, fallback_name=name)
        except XtreamError as exc:
            GLib.idle_add(self._series_error, token, account.id, sid, str(exc))
            return
        GLib.idle_add(self._series_done, token, account.id, sid, info)

    def _series_done(self, token: int, aid: str, sid: str, info: SeriesInfo) -> bool:
        if aid != self.active_account_id:
            return False
        self.series_info_cache[sid] = info
        if token != self.series_token:
            return False
        self.panel.enter_series(info)
        return False

    def _series_error(self, token: int, aid: str, sid: str, msg: str) -> bool:
        if token != self.series_token or aid != self.active_account_id:
            return False
        self.panel.show_series_error(msg)
        self._show_error(msg)
        return False

    # ── Events ──

    def _on_account_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self.ignore_combo:
            return
        aid = combo.get_active_id()
        if not aid:
            return
        self.active_account_id = aid
        self._persist()
        self._invalidate_cache()
        self.player.stop()
        self._load_catalog(force=True)

    def _on_manage_clicked(self, _btn: Gtk.Button) -> None:
        dlg = ManageAccountsDialog(self, self.accounts, self.active_account_id)
        try:
            if dlg.run() != Gtk.ResponseType.OK:
                return
            self.accounts = dlg.accounts
            self.active_account_id = dlg.active_account_id
            self._persist()
            if not self.accounts:
                self._rebuild_combo()
                self._handle_no_accounts()
                return
            if not self.active_account_id:
                self.active_account_id = self.accounts[0].id
            self._invalidate_cache()
            self.player.stop()
            self._rebuild_combo()
        finally:
            dlg.destroy()

    def _on_settings_clicked(self, _btn: Gtk.Button) -> None:
        settings = get_settings()
        dlg = SettingsDialog(self, settings)
        try:
            if dlg.run() == Gtk.ResponseType.OK and dlg.result_settings:
                save_settings(dlg.result_settings)
                # Apply volume immediately
                vol = dlg.result_settings.default_volume / 100
                self.player.set_default_volume(vol)
        finally:
            dlg.destroy()

    def _on_refresh(self, _btn: Gtk.Button) -> None:
        ct = self.panel.active_type
        self.catalog_loaded[ct] = False
        self._load_catalog(force=True)

    def _on_content_type_changed(self, kind: str) -> None:
        self._load_catalog()

    def _on_entry_activated(self, entry: CatalogEntry) -> None:
        self._play_entry(entry)

    def _on_series_selected(self, entry: CatalogEntry) -> None:
        self._load_series(entry)

    def _on_episode_activated(self, ep: SeriesEpisode) -> None:
        self._play_episode(ep)

    def _on_player_error(self, msg: str) -> None:
        self._update_np(t("playback_error"), msg)

    def _on_player_eos(self) -> None:
        self._update_np(t("stream_ended"))

    # ── Playback ──

    def _save_last_channel(self, entry_id: str, content_type: str) -> None:
        settings = get_settings()
        if not settings.remember_last_channel:
            return
        settings.last_channel_id = entry_id
        settings.last_channel_type = content_type
        settings.last_account_id = self.active_account_id or ""
        save_settings(settings)

    def _play_entry(self, entry: CatalogEntry) -> None:
        account = self._active_account()
        if not account:
            return
        try:
            uri = entry.playback_url(account)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        labels = content_labels()
        self.player.play(uri, entry.name, labels[entry.content_type])
        self._update_np(entry.name)
        self._save_last_channel(entry.id, entry.content_type)

    def _play_episode(self, ep: SeriesEpisode) -> None:
        account = self._active_account()
        if not account:
            return
        try:
            uri = ep.playback_url(account)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.player.play(uri, ep.title, ep.meta_line)
        self._update_np(ep.title)

    # ── Helpers ──

    def _show_error(self, msg: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        dialog.run()
        dialog.destroy()

    def _on_destroy(self, _w: Gtk.Window) -> None:
        self.player.destroy_resources()
