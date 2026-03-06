from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Pango

from ..i18n import t
from ..models import XtreamAccount
from .helpers import clear_listbox, make_label, suggest_account_name


def _entry_with_placeholder(placeholder: str, *, visibility: bool = True) -> Gtk.Entry:
    entry = Gtk.Entry()
    entry.set_placeholder_text(placeholder)
    entry.get_style_context().add_class("dlg-entry")
    entry.set_visibility(visibility)
    return entry


def _field_row(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    lbl = Gtk.Label(label=label_text)
    lbl.get_style_context().add_class("dlg-field-label")
    lbl.set_xalign(0)
    box.pack_start(lbl, False, False, 0)
    box.pack_start(widget, False, False, 0)
    return box


class AccountEditorDialog(Gtk.Dialog):
    def __init__(
        self,
        parent: Gtk.Window,
        account: XtreamAccount | None = None,
    ) -> None:
        title = t("edit_account") if account else t("new_account")
        super().__init__(
            title=title,
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        self.set_default_size(480, 0)

        self._existing_account = account
        self.result_account: XtreamAccount | None = None

        self.add_button(t("cancel"), Gtk.ResponseType.CANCEL)
        save_button = self.add_button(t("save"), Gtk.ResponseType.OK)
        save_button.get_style_context().add_class("action-btn")
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_border_width(20)
        content.set_spacing(16)

        # Account type selector
        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        type_box.set_margin_bottom(4)
        self._type_combo = Gtk.ComboBoxText()
        self._type_combo.get_style_context().add_class("dlg-entry")
        self._type_combo.append("xtream", "Xtream API")
        self._type_combo.append("m3u", t("m3u_playlist"))
        self._type_combo.connect("changed", self._on_type_changed)
        type_field = _field_row(t("account_type"), self._type_combo)
        content.pack_start(type_field, False, False, 0)

        # Name field (shared)
        self.name_entry = _entry_with_placeholder(t("account_name_placeholder"))
        content.pack_start(_field_row(t("account_name"), self.name_entry), False, False, 0)

        # Xtream fields
        self._xtream_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.server_entry = _entry_with_placeholder(t("server_placeholder"))
        self._xtream_box.pack_start(_field_row(t("server_address"), self.server_entry), False, False, 0)

        cred_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.username_entry = _entry_with_placeholder(t("username_placeholder"))
        self.password_entry = _entry_with_placeholder(t("password_placeholder"), visibility=False)
        user_field = _field_row(t("username"), self.username_entry)
        user_field.set_hexpand(True)
        pass_field = _field_row(t("password"), self.password_entry)
        pass_field.set_hexpand(True)
        cred_box.pack_start(user_field, True, True, 0)
        cred_box.pack_start(pass_field, True, True, 0)
        self._xtream_box.pack_start(cred_box, False, False, 0)
        content.pack_start(self._xtream_box, False, False, 0)

        # M3U fields
        self._m3u_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.m3u_entry = _entry_with_placeholder(t("m3u_url_placeholder"))
        self._m3u_box.pack_start(_field_row(t("m3u_url"), self.m3u_entry), False, False, 0)
        self._m3u_box.set_no_show_all(True)
        content.pack_start(self._m3u_box, False, False, 0)

        # Error label
        self.error_label = Gtk.Label(label="")
        self.error_label.get_style_context().add_class("dlg-error")
        self.error_label.set_line_wrap(True)
        self.error_label.set_xalign(0)
        self.error_label.set_no_show_all(True)
        content.pack_start(self.error_label, False, False, 0)

        # Fill existing account data
        if account is not None:
            self._type_combo.set_active_id(account.account_type)
            self.name_entry.set_text(account.name)
            if account.account_type == "m3u":
                self.m3u_entry.set_text(account.m3u_url)
            else:
                self.server_entry.set_text(account.server)
                self.username_entry.set_text(account.username)
                self.password_entry.set_text(account.password)
        else:
            self._type_combo.set_active_id("xtream")

        self._update_fields_visibility()

        self.connect("response", self._on_response)
        self.show_all()
        self.error_label.hide()
        self._update_fields_visibility()

    def _on_type_changed(self, _combo: Gtk.ComboBoxText) -> None:
        self._update_fields_visibility()

    def _update_fields_visibility(self) -> None:
        is_m3u = self._type_combo.get_active_id() == "m3u"
        if is_m3u:
            self._xtream_box.hide()
            self._xtream_box.set_no_show_all(True)
            self._m3u_box.set_no_show_all(False)
            self._m3u_box.show_all()
        else:
            self._m3u_box.hide()
            self._m3u_box.set_no_show_all(True)
            self._xtream_box.set_no_show_all(False)
            self._xtream_box.show_all()

    def _on_response(self, _dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            self.result_account = None
            return
        try:
            self.result_account = self._build_account()
        except ValueError as exc:
            self.result_account = None
            self.error_label.set_text(str(exc))
            self.error_label.show()
            self.stop_emission_by_name("response")

    def _build_account(self) -> XtreamAccount:
        account_type = self._type_combo.get_active_id() or "xtream"

        if account_type == "m3u":
            m3u_url = self.m3u_entry.get_text().strip()
            if not m3u_url:
                raise ValueError(t("m3u_url_required"))
            name = self.name_entry.get_text().strip() or "M3U Playlist"

            if self._existing_account is None:
                return XtreamAccount.create(
                    name=name, account_type="m3u", m3u_url=m3u_url,
                )
            return XtreamAccount(
                id=self._existing_account.id,
                name=name, server="", username="", password="",
                account_type="m3u", m3u_url=m3u_url,
            )

        # Xtream
        server = self.server_entry.get_text().strip()
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()

        if not server:
            raise ValueError(t("server_required"))
        if not username:
            raise ValueError(t("username_required"))
        if not password:
            raise ValueError(t("password_required"))

        name = self.name_entry.get_text().strip() or suggest_account_name(server, username)

        if self._existing_account is None:
            account = XtreamAccount.create(
                name=name, server=server, username=username,
                password=password,
            )
        else:
            account = XtreamAccount(
                id=self._existing_account.id,
                name=name, server=server, username=username,
                password=password,
            )
        _ = account.normalized_server
        return account


class ManageAccountsDialog(Gtk.Dialog):
    def __init__(
        self,
        parent: Gtk.Window,
        accounts: list[XtreamAccount],
        active_account_id: str | None,
    ) -> None:
        super().__init__(
            title=t("manage_accounts"),
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        self.set_default_size(520, 420)

        self.accounts = [XtreamAccount.from_dict(a.to_dict()) for a in accounts]
        self.active_account_id = active_account_id or (
            self.accounts[0].id if self.accounts else None
        )

        self.add_button(t("cancel"), Gtk.ResponseType.CANCEL)
        apply_button = self.add_button(t("apply"), Gtk.ResponseType.OK)
        apply_button.get_style_context().add_class("action-btn")
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_border_width(16)
        content.set_spacing(12)

        # Account list
        self.listbox = Gtk.ListBox()
        self.listbox.get_style_context().add_class("dlg-account-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._on_row_selected)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.add(self.listbox)
        content.pack_start(scrolled, True, True, 0)

        # Action buttons
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.add_btn = Gtk.Button()
        add_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_inner.pack_start(Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        add_inner.pack_start(Gtk.Label(label=t("add")), False, False, 0)
        self.add_btn.add(add_inner)
        self.add_btn.get_style_context().add_class("action-btn")
        self.add_btn.connect("clicked", self._on_add)
        buttons.pack_start(self.add_btn, False, False, 0)

        self.edit_btn = Gtk.Button()
        edit_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        edit_inner.pack_start(Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        edit_inner.pack_start(Gtk.Label(label=t("edit")), False, False, 0)
        self.edit_btn.add(edit_inner)
        self.edit_btn.get_style_context().add_class("dlg-action-secondary")
        self.edit_btn.connect("clicked", self._on_edit)
        buttons.pack_start(self.edit_btn, False, False, 0)

        self.delete_btn = Gtk.Button()
        del_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        del_inner.pack_start(Gtk.Image.new_from_icon_name("edit-delete-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        del_inner.pack_start(Gtk.Label(label=t("delete")), False, False, 0)
        self.delete_btn.add(del_inner)
        self.delete_btn.get_style_context().add_class("dlg-action-danger")
        self.delete_btn.connect("clicked", self._on_delete)
        buttons.pack_end(self.delete_btn, False, False, 0)

        content.pack_start(buttons, False, False, 0)

        self._refresh()
        self.show_all()

    def _on_row_selected(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        aid = getattr(row, "account_id", None)
        if aid:
            self.active_account_id = aid
        has = row is not None and aid is not None
        self.edit_btn.set_sensitive(has)
        self.delete_btn.set_sensitive(has)

    def _on_add(self, _btn: Gtk.Button) -> None:
        dlg = AccountEditorDialog(self)
        try:
            if dlg.run() == Gtk.ResponseType.OK and dlg.result_account:
                self.accounts.append(dlg.result_account)
                self.active_account_id = dlg.result_account.id
                self._refresh()
        finally:
            dlg.destroy()

    def _on_edit(self, _btn: Gtk.Button) -> None:
        account = self._selected()
        if not account:
            return
        dlg = AccountEditorDialog(self, account)
        try:
            if dlg.run() == Gtk.ResponseType.OK and dlg.result_account:
                for i, a in enumerate(self.accounts):
                    if a.id == account.id:
                        self.accounts[i] = dlg.result_account
                        break
                self.active_account_id = dlg.result_account.id
                self._refresh()
        finally:
            dlg.destroy()

    def _on_delete(self, _btn: Gtk.Button) -> None:
        account = self._selected()
        if not account:
            return
        confirm = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=t("delete_confirm"),
        )
        confirm.format_secondary_text(account.name)
        try:
            if confirm.run() == Gtk.ResponseType.OK:
                self.accounts = [a for a in self.accounts if a.id != account.id]
                if self.active_account_id == account.id:
                    self.active_account_id = (
                        self.accounts[0].id if self.accounts else None
                    )
                self._refresh()
        finally:
            confirm.destroy()

    def _refresh(self) -> None:
        clear_listbox(self.listbox)

        if not self.accounts:
            row = Gtk.ListBoxRow(selectable=False, activatable=False)
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            empty_box.set_halign(Gtk.Align.CENTER)
            empty_box.set_valign(Gtk.Align.CENTER)
            empty_box.set_margin_top(40)
            empty_box.set_margin_bottom(40)
            icon = Gtk.Image.new_from_icon_name("system-users-symbolic", Gtk.IconSize.DIALOG)
            icon.get_style_context().add_class("dim-text")
            empty_box.pack_start(icon, False, False, 0)
            empty_box.pack_start(make_label(t("no_accounts"), css="dim-text"), False, False, 0)
            empty_box.pack_start(make_label(t("no_accounts_sub"), css="dim-text"), False, False, 0)
            row.add(empty_box)
            self.listbox.add(row)
            self.listbox.show_all()
            self.edit_btn.set_sensitive(False)
            self.delete_btn.set_sensitive(False)
            return

        for account in self.accounts:
            row = Gtk.ListBoxRow()
            row.account_id = account.id

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(10)
            box.set_margin_bottom(10)
            box.set_margin_start(14)
            box.set_margin_end(14)

            # Avatar circle
            avatar = Gtk.Label(label=account.name[0].upper() if account.name else "?")
            avatar.get_style_context().add_class("dlg-avatar")
            avatar.set_size_request(36, 36)
            box.pack_start(avatar, False, False, 0)

            # Account info
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info.set_valign(Gtk.Align.CENTER)
            name_lbl = Gtk.Label(label=account.name)
            name_lbl.get_style_context().add_class("dlg-account-name")
            name_lbl.set_xalign(0)
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            info.pack_start(name_lbl, False, False, 0)

            if account.account_type == "m3u":
                detail_text = f"M3U - {account.m3u_url[:50]}"
            else:
                detail_text = f"{account.username} @ {account.host_label}"
            detail_lbl = Gtk.Label(label=detail_text)
            detail_lbl.get_style_context().add_class("dlg-account-detail")
            detail_lbl.set_xalign(0)
            detail_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            info.pack_start(detail_lbl, False, False, 0)
            box.pack_start(info, True, True, 0)

            # Active badge
            if account.id == self.active_account_id:
                badge = Gtk.Label(label=t("active"))
                badge.get_style_context().add_class("pill")
                badge.get_style_context().add_class("pill-active")
                badge.set_valign(Gtk.Align.CENTER)
                box.pack_end(badge, False, False, 0)

            row.add(box)
            self.listbox.add(row)

        self.listbox.show_all()
        self._select_id(self.active_account_id)

    def _select_id(self, account_id: str | None) -> None:
        if not account_id:
            return
        for row in self.listbox.get_children():
            if getattr(row, "account_id", None) == account_id:
                self.listbox.select_row(row)
                return

    def _selected(self) -> XtreamAccount | None:
        row = self.listbox.get_selected_row()
        aid = getattr(row, "account_id", None)
        for a in self.accounts:
            if a.id == aid:
                return a
        return None
