from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from ..i18n import LANGUAGES, t
from ..settings import AppSettings


def _section_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.get_style_context().add_class("settings-section")
    lbl.set_xalign(0)
    lbl.set_margin_top(8)
    return lbl


def _setting_row(
    label: str, widget: Gtk.Widget, *, desc: str | None = None
) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.get_style_context().add_class("settings-row")
    row.set_margin_top(4)
    row.set_margin_bottom(4)
    row.set_margin_start(8)
    row.set_margin_end(8)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    text_box.set_valign(Gtk.Align.CENTER)
    name_lbl = Gtk.Label(label=label)
    name_lbl.get_style_context().add_class("settings-label")
    name_lbl.set_xalign(0)
    text_box.pack_start(name_lbl, False, False, 0)
    if desc:
        desc_lbl = Gtk.Label(label=desc)
        desc_lbl.get_style_context().add_class("settings-desc")
        desc_lbl.set_xalign(0)
        text_box.pack_start(desc_lbl, False, False, 0)
    row.pack_start(text_box, True, True, 0)

    widget.set_valign(Gtk.Align.CENTER)
    row.pack_end(widget, False, False, 0)
    return row


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, settings: AppSettings) -> None:
        super().__init__(
            title=t("settings_title"),
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        self.set_default_size(500, 0)

        self.result_settings: AppSettings | None = None
        self._settings = settings

        self.add_button(t("cancel"), Gtk.ResponseType.CANCEL)
        save_btn = self.add_button(t("save"), Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("action-btn")
        self.set_default_response(Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_border_width(16)
        content.set_spacing(6)

        # ── General ──
        content.pack_start(_section_label(t("general")), False, False, 0)

        self.lang_combo = Gtk.ComboBoxText()
        self.lang_combo.get_style_context().add_class("dlg-entry")
        for code, name in LANGUAGES.items():
            self.lang_combo.append(code, name)
        self.lang_combo.set_active_id(settings.language)
        content.pack_start(_setting_row(t("language"), self.lang_combo), False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep1.set_margin_top(8)
        sep1.set_margin_bottom(4)
        content.pack_start(sep1, False, False, 0)

        # ── Playback ──
        content.pack_start(_section_label(t("playback")), False, False, 0)

        self.output_combo = Gtk.ComboBoxText()
        self.output_combo.get_style_context().add_class("dlg-entry")
        self.output_combo.append("ts", "TS (MPEG-TS)")
        self.output_combo.append("m3u8", "M3U8 (HLS)")
        self.output_combo.set_active_id(settings.live_output)
        content.pack_start(
            _setting_row(t("live_output_format"), self.output_combo), False, False, 0
        )

        self.buffer_combo = Gtk.ComboBoxText()
        self.buffer_combo.get_style_context().add_class("dlg-entry")
        self.buffer_combo.append("low", t("buffer_low"))
        self.buffer_combo.append("normal", t("buffer_normal"))
        self.buffer_combo.append("high", t("buffer_high"))
        self.buffer_combo.set_active_id(settings.buffer_mode)
        content.pack_start(
            _setting_row(t("buffer_mode"), self.buffer_combo, desc=t("buffer_mode_desc")),
            False, False, 0,
        )

        self.deinterlace_combo = Gtk.ComboBoxText()
        self.deinterlace_combo.get_style_context().add_class("dlg-entry")
        self.deinterlace_combo.append("off", t("deinterlace_off"))
        self.deinterlace_combo.append("auto", t("deinterlace_auto"))
        self.deinterlace_combo.append("on", t("deinterlace_on"))
        self.deinterlace_combo.set_active_id(settings.deinterlace)
        content.pack_start(
            _setting_row(t("deinterlace"), self.deinterlace_combo, desc=t("deinterlace_desc")),
            False, False, 0,
        )

        self.vol_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 150, 5
        )
        self.vol_scale.set_value(settings.default_volume)
        self.vol_scale.set_size_request(160, -1)
        self.vol_scale.set_draw_value(True)
        self.vol_scale.get_style_context().add_class("settings-scale")
        content.pack_start(
            _setting_row(t("default_volume"), self.vol_scale), False, False, 0
        )

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(8)
        sep2.set_margin_bottom(4)
        content.pack_start(sep2, False, False, 0)

        # ── Interface ──
        content.pack_start(_section_label(t("interface")), False, False, 0)

        self.maximized_switch = Gtk.Switch()
        self.maximized_switch.set_active(settings.start_maximized)
        content.pack_start(
            _setting_row(
                t("start_maximized"), self.maximized_switch,
                desc=t("start_maximized_desc"),
            ),
            False, False, 0,
        )

        self.remember_switch = Gtk.Switch()
        self.remember_switch.set_active(settings.remember_last_channel)
        content.pack_start(
            _setting_row(
                t("remember_last"), self.remember_switch,
                desc=t("remember_last_desc"),
            ),
            False, False, 0,
        )

        sep3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep3.set_margin_top(8)
        sep3.set_margin_bottom(4)
        content.pack_start(sep3, False, False, 0)

        # ── About ──
        content.pack_start(_section_label(t("about")), False, False, 0)

        about_text = Gtk.Label(label=t("about_text"))
        about_text.set_xalign(0)
        about_text.set_line_wrap(True)
        about_text.set_max_width_chars(60)
        about_text.get_style_context().add_class("settings-desc")
        about_text.set_margin_start(8)
        about_text.set_margin_end(8)
        about_text.set_margin_top(4)
        content.pack_start(about_text, False, False, 0)

        ver_label = Gtk.Label(label=f"{t('about_version')}: 1.0")
        ver_label.set_xalign(0)
        ver_label.get_style_context().add_class("settings-desc")
        ver_label.set_margin_start(8)
        ver_label.set_margin_top(6)
        content.pack_start(ver_label, False, False, 0)

        mail_label = Gtk.Label(label=f"{t('about_contact')}: zfrdmr@protonmail.com")
        mail_label.set_xalign(0)
        mail_label.get_style_context().add_class("settings-desc")
        mail_label.set_margin_start(8)
        mail_label.set_margin_top(2)
        mail_label.set_selectable(True)
        content.pack_start(mail_label, False, False, 0)

        # Restart notice
        self._notice = Gtk.Label(label="")
        self._notice.get_style_context().add_class("settings-notice")
        self._notice.set_xalign(0)
        self._notice.set_margin_top(12)
        self._notice.set_no_show_all(True)
        content.pack_start(self._notice, False, False, 0)

        self.lang_combo.connect("changed", self._on_lang_changed)
        self.connect("response", self._on_response)
        self.show_all()
        self._notice.hide()

    def _on_lang_changed(self, _combo: Gtk.ComboBoxText) -> None:
        new_lang = self.lang_combo.get_active_id()
        if new_lang and new_lang != self._settings.language:
            self._notice.set_text(t("restart_required"))
            self._notice.set_no_show_all(False)
            self._notice.show()
        else:
            self._notice.hide()
            self._notice.set_no_show_all(True)

    def _on_response(self, _dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            self.result_settings = None
            return
        # Preserve fields managed elsewhere
        prev = self._settings
        self.result_settings = AppSettings(
            language=self.lang_combo.get_active_id() or "tr",
            live_output=self.output_combo.get_active_id() or "ts",
            default_volume=int(self.vol_scale.get_value()),
            buffer_mode=self.buffer_combo.get_active_id() or "normal",
            deinterlace=self.deinterlace_combo.get_active_id() or "auto",
            start_maximized=self.maximized_switch.get_active(),
            remember_last_channel=self.remember_switch.get_active(),
            last_channel_id=prev.last_channel_id,
            last_channel_type=prev.last_channel_type,
            last_account_id=prev.last_account_id,
            color_brightness=prev.color_brightness,
            color_contrast=prev.color_contrast,
            color_saturation=prev.color_saturation,
            color_hue=prev.color_hue,
        )
