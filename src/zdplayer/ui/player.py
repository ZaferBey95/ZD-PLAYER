from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gdk, GLib, Gst, Gtk

from ..i18n import t
from ..settings import get_settings, save_settings
from .helpers import make_icon_button, make_label

SEEK_STEP_NS = 10 * Gst.SECOND  # 10 seconds
POSITION_POLL_MS = 500
SEEK_DEBOUNCE_MS = 80
SEEK_DISPLAY_GRACE_US = 900_000

BUFFER_DURATIONS = {
    "low": 1 * Gst.SECOND,
    "normal": 3 * Gst.SECOND,
    "high": 10 * Gst.SECOND,
}


def _format_time(ns: int) -> str:
    if ns < 0:
        return "00:00"
    total_sec = ns // Gst.SECOND
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class PlayerWidget(Gtk.Box):
    def __init__(
        self,
        *,
        on_error: Callable[[str], None] | None = None,
        on_eos: Callable[[], None] | None = None,
        on_prev_item: Callable[[], None] | None = None,
        on_next_item: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._on_error = on_error
        self._on_eos = on_eos
        self._on_prev_item = on_prev_item
        self._on_next_item = on_next_item

        self._current_title: str | None = None
        self._current_meta: str | None = None
        self._paused = False
        self._fullscreen = False
        self._volume = 0.75
        self._last_nonzero_volume = self._volume
        self._vol_popup_timer = 0
        self._track_gen = 0
        self._ignore_track = False

        # Seek state
        self._seeking = False
        self._duration_ns: int = 0
        self._position_timer = 0
        self._seek_pending_timer = 0
        self._seek_target_ns: int = -1
        self._pending_seek_display_ns: int = -1
        self._pending_seek_deadline_us: int = 0
        self._measured_fps_text = ""

        # Color balance (range: -1.0 to 1.0, default 0.0)
        _s = get_settings()
        self._brightness = _s.color_brightness
        self._contrast = _s.color_contrast
        self._saturation = _s.color_saturation
        self._hue = _s.color_hue

        self._fs_window: Gtk.Window | None = None
        self._fs_accel_group: Gtk.AccelGroup | None = None
        self._fs_event_box: Gtk.EventBox | None = None
        self._fs_video_box: Gtk.Box | None = None
        self._fs_controls_revealer: Gtk.Revealer | None = None
        self._fs_title: Gtk.Label | None = None
        self._fs_hide_timer = 0
        self._fs_seek_scale: Gtk.Scale | None = None
        self._fs_time_current: Gtk.Label | None = None
        self._fs_time_total: Gtk.Label | None = None
        self._fs_pp_btn: Gtk.Button | None = None
        self._vol_icon: Gtk.Image | None = None
        self._fs_vol_icon: Gtk.Image | None = None
        self._vol_button: Gtk.Button | None = None
        self._fs_vol_button: Gtk.Button | None = None
        self._vol_popover: Gtk.Popover | None = None
        self._fs_vol_popover: Gtk.Popover | None = None
        self._vol_scale: Gtk.Scale | None = None
        self._fs_vol_scale: Gtk.Scale | None = None
        self._vol_popover_icon: Gtk.Image | None = None
        self._fs_vol_popover_icon: Gtk.Image | None = None
        self._vol_popover_value: Gtk.Label | None = None
        self._fs_vol_popover_value: Gtk.Label | None = None
        self._ignore_volume_scale = False

        self._init_gst()
        self._build()

    # ── GStreamer setup ──

    def _init_gst(self) -> None:
        self.playbin = Gst.ElementFactory.make("playbin", "player")
        self.video_sink = Gst.ElementFactory.make("gtksink", "vsink")
        self._fps_sink = Gst.ElementFactory.make("fpsdisplaysink", "fpssink")
        if not self.playbin or not self.video_sink:
            raise RuntimeError("GStreamer player could not be created.")
        if self._fps_sink:
            self._fps_sink.set_property("text-overlay", False)
            self._fps_sink.set_property("video-sink", self.video_sink)
            self._fps_sink.set_property("signal-fps-measurements", True)
            self._fps_sink.set_property("fps-update-interval", 750)
            self._fps_sink.connect("fps-measurements", self._on_fps_measurements)

        self._videobalance = Gst.ElementFactory.make("videobalance", "vbalance")
        self._build_video_pipeline()
        self._apply_color_balance()
        self.playbin.set_property("volume", self._volume)
        self.playbin.connect("source-setup", self._on_source_setup)
        self.video_widget = self.video_sink.props.widget
        self._configure_video_widget()
        self.video_widget.set_hexpand(True)
        self.video_widget.set_vexpand(True)

        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_gst_msg)

    def _on_source_setup(self, _playbin: Gst.Element, source: Gst.Element) -> None:
        if source.find_property("user-agent"):
            source.set_property("user-agent", "ZD PLAYER")

    def _build_video_pipeline(self) -> None:
        settings = get_settings()
        mode = settings.deinterlace

        elements: list[Gst.Element] = []
        terminal_sink = self._fps_sink or self.video_sink

        # Deinterlace
        if mode != "off":
            deinterlace = Gst.ElementFactory.make("deinterlace", "deinterlace")
            if deinterlace:
                if mode == "on":
                    deinterlace.set_property("mode", 1)
                else:
                    deinterlace.set_property("mode", 0)
                elements.append(deinterlace)

        # Video balance
        if self._videobalance:
            elements.append(self._videobalance)

        if not elements:
            self.playbin.set_property("video-sink", terminal_sink)
            return

        vbin = Gst.Bin.new("vsinkbin")
        for el in elements:
            vbin.add(el)
        vbin.add(terminal_sink)

        # Link chain: elements... -> terminal sink
        chain = elements + [terminal_sink]
        for i in range(len(chain) - 1):
            chain[i].link(chain[i + 1])

        pad = chain[0].get_static_pad("sink")
        ghost = Gst.GhostPad.new("sink", pad)
        vbin.add_pad(ghost)

        self.playbin.set_property("video-sink", vbin)

    def _configure_video_widget(self) -> None:
        if self.video_widget is None:
            return
        if hasattr(self.video_widget, "set_can_focus"):
            self.video_widget.set_can_focus(True)
        if hasattr(self.video_widget, "add_events"):
            self.video_widget.add_events(
                Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
            )
        if hasattr(self.video_widget, "connect"):
            self.video_widget.connect("key-press-event", self._on_playback_key)
            self.video_widget.connect("button-press-event", self._on_video_button_press)

    # ── UI build ──

    def _build(self) -> None:
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(200)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)
        self.stack.set_hhomogeneous(True)
        self.stack.set_vhomogeneous(True)
        self.pack_start(self.stack, True, True, 0)

        # Empty page
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        empty.get_style_context().add_class("player-empty-box")
        empty.set_halign(Gtk.Align.FILL)
        empty.set_valign(Gtk.Align.FILL)
        empty.set_hexpand(True)
        empty.set_vexpand(True)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        self.empty_title = make_label(t("app_name"), css="player-empty-title", xalign=0.5)
        self.empty_sub = make_label(
            t("select_content"),
            css="player-empty-sub", xalign=0.5, wrap=True,
        )
        self.empty_btn = Gtk.Button(label=t("manage_accounts_btn"))
        self.empty_btn.get_style_context().add_class("action-btn")
        self.empty_btn.set_halign(Gtk.Align.CENTER)
        center.pack_start(self.empty_title, False, False, 0)
        center.pack_start(self.empty_sub, False, False, 0)
        center.pack_start(self.empty_btn, False, False, 8)
        empty.pack_start(center, True, True, 0)
        self.stack.add_named(empty, "empty")

        # Video page
        overlay = Gtk.Overlay()
        self._event_box = Gtk.EventBox()
        self._event_box.add_events(
            Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self._event_box.set_can_focus(True)
        self._event_box.connect("scroll-event", self._on_scroll)
        self._event_box.connect("button-press-event", self._on_video_button_press)
        self._event_box.connect("key-press-event", self._on_playback_key)

        self._video_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._video_shell.get_style_context().add_class("video-area")
        self._video_shell.pack_start(self.video_widget, True, True, 0)
        self._event_box.add(self._video_shell)
        overlay.add(self._event_box)

        # Volume popup overlay
        self._vol_popup = make_label("", css="vol-popup")
        self._vol_popup.set_halign(Gtk.Align.CENTER)
        self._vol_popup.set_valign(Gtk.Align.CENTER)
        self._vol_popup.set_no_show_all(True)
        overlay.add_overlay(self._vol_popup)

        self.stack.add_named(overlay, "video")

        # Seek bar row
        self._build_seek_bar()

        # Control bar
        self._build_controls()
        self.stack.set_visible_child_name("empty")

    def _build_volume_popover(
        self, relative_to: Gtk.Widget
    ) -> tuple[Gtk.Popover, Gtk.Scale, Gtk.Image, Gtk.Label]:
        popover = Gtk.Popover.new(relative_to)
        popover.set_position(Gtk.PositionType.TOP)
        popover.get_style_context().add_class("volume-popover")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("vol-popover-box")
        box.set_border_width(12)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.get_style_context().add_class("vol-popover-head")

        icon = Gtk.Image.new_from_icon_name(self._volume_icon_name(), Gtk.IconSize.MENU)
        icon.get_style_context().add_class("vol-popover-icon")
        head.pack_start(icon, False, False, 0)

        title = make_label(t("volume_control"), css="vol-popover-title")
        head.pack_start(title, True, True, 0)

        value = make_label(self._vol_text(), css="vol-popover-value", xalign=1.0)
        head.pack_start(value, False, False, 0)
        box.pack_start(head, False, False, 0)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_size_request(196, -1)
        scale.get_style_context().add_class("settings-scale")
        scale.get_style_context().add_class("volume-scale")
        scale.connect("value-changed", self._on_volume_scale_changed)
        box.pack_start(scale, False, False, 0)

        popover.add(box)
        return popover, scale, icon, value

    def _build_seek_bar(self) -> None:
        seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        seek_row.get_style_context().add_class("seek-row")
        seek_row.set_margin_top(6)
        seek_row.set_margin_start(10)
        seek_row.set_margin_end(10)
        self.pack_start(seek_row, False, False, 0)

        self.time_current = make_label("00:00", css="time-label")
        seek_row.pack_start(self.time_current, False, False, 0)

        self.seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.set_hexpand(True)
        self.seek_scale.get_style_context().add_class("seek-slider")
        self.seek_scale.connect("button-press-event", self._on_seek_start)
        self.seek_scale.connect("button-release-event", self._on_seek_end)
        self.seek_scale.connect("value-changed", self._on_seek_value_changed)
        seek_row.pack_start(self.seek_scale, True, True, 0)

        self.time_total = make_label("00:00", css="time-label")
        seek_row.pack_start(self.time_total, False, False, 0)

    def _build_controls(self) -> None:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.get_style_context().add_class("control-bar")
        bar.set_margin_top(4)
        bar.set_margin_start(4)
        bar.set_margin_end(4)
        bar.set_margin_bottom(4)
        self.pack_start(bar, False, False, 0)

        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        transport.get_style_context().add_class("ctrl-cluster")
        transport.get_style_context().add_class("ctrl-cluster-transport")
        bar.pack_start(transport, False, False, 0)

        self.btn_prev = make_icon_button(
            "media-skip-backward-symbolic", t("previous_content"), css="ctrl-btn-nav",
        )
        self.btn_prev.connect("clicked", self._on_prev_item_click)
        transport.pack_start(self.btn_prev, False, False, 0)

        self.btn_seek_back = make_icon_button(
            "media-seek-backward-symbolic",
            t("skip_back_short"),
            css="ctrl-btn-small",
            size=Gtk.IconSize.MENU,
        )
        self.btn_seek_back.connect("clicked", self._on_skip_back)
        transport.pack_start(self.btn_seek_back, False, False, 0)

        self.btn_play = make_icon_button(
            "media-playback-start-symbolic", t("play_pause"), css="ctrl-btn-accent",
        )
        self.btn_play.connect("clicked", self._on_play_pause)
        transport.pack_start(self.btn_play, False, False, 0)

        self.btn_seek_fwd = make_icon_button(
            "media-seek-forward-symbolic",
            t("skip_forward_short"),
            css="ctrl-btn-small",
            size=Gtk.IconSize.MENU,
        )
        self.btn_seek_fwd.connect("clicked", self._on_skip_forward)
        transport.pack_start(self.btn_seek_fwd, False, False, 0)

        self.btn_next = make_icon_button(
            "media-skip-forward-symbolic", t("next_content"), css="ctrl-btn-nav",
        )
        self.btn_next.connect("clicked", self._on_next_item_click)
        transport.pack_start(self.btn_next, False, False, 0)

        self.btn_stop = make_icon_button(
            "media-playback-stop-symbolic", t("stop"), css="ctrl-btn",
        )
        self.btn_stop.connect("clicked", self._on_stop_click)
        transport.pack_start(self.btn_stop, False, False, 0)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.set_valign(Gtk.Align.CENTER)
        titles.get_style_context().add_class("ctrl-title-block")
        self.ctrl_title = make_label(t("app_name"), css="ctrl-title", ellipsize=True)
        self.ctrl_meta = make_label(t("waiting_content"), css="ctrl-meta", ellipsize=True)
        titles.pack_start(self.ctrl_title, False, False, 0)
        titles.pack_start(self.ctrl_meta, False, False, 0)
        bar.pack_start(titles, True, True, 0)

        # Stream stats
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stats_box.set_valign(Gtk.Align.CENTER)
        stats_box.get_style_context().add_class("stats-cluster")
        self._res_label = make_label("", css="stream-stat")
        self._fps_label = make_label("", css="stream-stat")
        self._bitrate_label = make_label("", css="stream-stat")
        stats_box.pack_start(self._res_label, False, False, 0)
        stats_box.pack_start(self._fps_label, False, False, 0)
        stats_box.pack_start(self._bitrate_label, False, False, 0)
        bar.pack_start(stats_box, False, False, 4)

        utility = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        utility.get_style_context().add_class("ctrl-cluster")
        utility.get_style_context().add_class("ctrl-cluster-utility")
        bar.pack_start(utility, False, False, 0)

        vol_button = Gtk.Button()
        vol_button.get_style_context().add_class("vol-chip-btn")
        vol_button.set_tooltip_text(t("volume_control"))
        vol_button.connect("clicked", self._on_volume_chip_click)
        self._vol_button = vol_button

        vol_chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vol_chip.get_style_context().add_class("vol-chip")
        self._vol_icon = Gtk.Image.new_from_icon_name(
            self._volume_icon_name(), Gtk.IconSize.MENU
        )
        self._vol_icon.get_style_context().add_class("vol-chip-icon")
        vol_chip.pack_start(self._vol_icon, False, False, 0)
        self.vol_label = make_label(self._vol_text(), css="vol-label")
        vol_chip.pack_start(self.vol_label, False, False, 0)
        vol_button.add(vol_chip)
        utility.pack_start(vol_button, False, False, 0)
        (
            self._vol_popover,
            self._vol_scale,
            self._vol_popover_icon,
            self._vol_popover_value,
        ) = self._build_volume_popover(vol_button)

        self.btn_fs = make_icon_button(
            "view-fullscreen-symbolic", t("fullscreen"), css="ctrl-btn-utility",
        )
        self.btn_fs.connect("clicked", self._on_fs_click)
        utility.pack_start(self.btn_fs, False, False, 0)

        self._set_controls_sensitive(False)

    def _set_controls_sensitive(self, on: bool) -> None:
        self.btn_play.set_sensitive(on)
        self.btn_stop.set_sensitive(on)
        self.btn_fs.set_sensitive(on)
        self.btn_prev.set_sensitive(on)
        self.btn_next.set_sensitive(on)
        self.btn_seek_back.set_sensitive(on)
        self.btn_seek_fwd.set_sensitive(on)
        self.seek_scale.set_sensitive(on)

    # ── Stream stats ──

    def _update_stream_stats(self) -> None:
        fps_text = self._measured_fps_text
        bitrate_text = ""
        res_text = ""
        try:
            sink = self.playbin.get_property("video-sink")
            if sink:
                pad = sink.get_static_pad("sink")
                if pad:
                    caps = pad.get_current_caps()
                    if caps and caps.get_size() > 0:
                        st = caps.get_structure(0)
                        ok, num, den = st.get_fraction("framerate")
                        if not fps_text and ok and den > 0:
                            fps = num / den
                            fps_text = self._format_fps_text(fps)
                        ok, w = st.get_int("width")
                        ok2, h = st.get_int("height")
                        if ok and ok2 and w > 0 and h > 0:
                            res_text = f"{w}x{h}"
        except Exception:
            pass

        try:
            tags = self.playbin.emit("get-video-tags", 0)
            if tags:
                ok, br = tags.get_uint("bitrate")
                if ok and br > 0:
                    if br >= 1_000_000:
                        bitrate_text = f"{br / 1_000_000:.1f} Mbps"
                    else:
                        bitrate_text = f"{br // 1000} Kbps"
                else:
                    ok, br = tags.get_uint("nominal-bitrate")
                    if ok and br > 0:
                        if br >= 1_000_000:
                            bitrate_text = f"{br / 1_000_000:.1f} Mbps"
                        else:
                            bitrate_text = f"{br // 1000} Kbps"
        except Exception:
            pass

        self._res_label.set_text(res_text)
        self._fps_label.set_text(fps_text)
        self._bitrate_label.set_text(bitrate_text)
        if self._fullscreen and hasattr(self, '_fs_res_label'):
            self._fs_res_label.set_text(res_text)
            self._fs_fps_label.set_text(fps_text)
            self._fs_bitrate_label.set_text(bitrate_text)

    def _clear_stream_stats(self) -> None:
        self._measured_fps_text = ""
        self._res_label.set_text("")
        self._fps_label.set_text("")
        self._bitrate_label.set_text("")
        if hasattr(self, '_fs_res_label'):
            self._fs_res_label.set_text("")
            self._fs_fps_label.set_text("")
            self._fs_bitrate_label.set_text("")

    def _format_fps_text(self, fps: float) -> str:
        if fps <= 0:
            return ""
        rounded = round(fps)
        if abs(fps - rounded) < 0.08:
            return f"{rounded:.0f} FPS"
        text = f"{fps:.2f}".rstrip("0").rstrip(".")
        return f"{text} FPS"

    def _apply_measured_fps_text(self, text: str) -> bool:
        if self._current_title is None:
            return False
        self._measured_fps_text = text
        self._fps_label.set_text(text)
        if self._fullscreen and hasattr(self, "_fs_fps_label"):
            self._fs_fps_label.set_text(text)
        return False

    def _on_fps_measurements(
        self,
        _sink: Gst.Element,
        fps: float,
        _droprate: float,
        avgfps: float,
    ) -> None:
        value = avgfps if avgfps > 0 else fps
        if value <= 0:
            return
        GLib.idle_add(self._apply_measured_fps_text, self._format_fps_text(value))

    # ── Time / seek helpers ──

    def _query_duration(self) -> int:
        ok, dur = self.playbin.query_duration(Gst.Format.TIME)
        return dur if ok and dur > 0 else 0

    def _query_position(self) -> int:
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        return pos if ok and pos >= 0 else 0

    def _effective_position(self) -> int:
        pos = self._query_position()
        if pos > 0:
            return pos
        if self._pending_seek_display_ns >= 0:
            return self._pending_seek_display_ns
        if self._duration_ns > 0:
            frac = self.seek_scale.get_value() / 1000
            return int(frac * self._duration_ns)
        return 0

    def _set_position_display(self, pos_ns: int, dur_ns: int | None = None) -> None:
        pos_ns = max(0, pos_ns)
        dur = dur_ns if dur_ns is not None else self._duration_ns
        self.time_current.set_text(_format_time(pos_ns))
        if self._fs_time_current is not None:
            self._fs_time_current.set_text(_format_time(pos_ns))
        if dur <= 0:
            return
        frac = min(max(pos_ns / dur, 0.0), 1.0)
        self.time_total.set_text(_format_time(dur))
        if self._fs_time_total is not None:
            self._fs_time_total.set_text(_format_time(dur))
        self.seek_scale.set_value(frac * 1000)
        if self._fs_seek_scale is not None:
            self._fs_seek_scale.set_value(frac * 1000)

    def _is_seekable(self) -> bool:
        _, state, _ = self.playbin.get_state(0)
        return state in (Gst.State.PLAYING, Gst.State.PAUSED)

    def _seek_to(self, position_ns: int) -> None:
        if not self._is_seekable():
            return
        position_ns = max(0, position_ns)
        self._pending_seek_display_ns = position_ns
        self._pending_seek_deadline_us = GLib.get_monotonic_time() + SEEK_DISPLAY_GRACE_US
        dur = self._duration_ns or self._query_duration()
        self._set_position_display(position_ns, dur if dur > 0 else None)
        try:
            self.playbin.seek(
                1.0,
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                Gst.SeekType.SET,
                position_ns,
                Gst.SeekType.NONE,
                0,
            )
        except Exception:
            pass

    def _seek_to_debounced(self, position_ns: int) -> None:
        self._seek_target_ns = max(0, position_ns)
        if self._seek_pending_timer:
            return
        self._seek_pending_timer = GLib.timeout_add(SEEK_DEBOUNCE_MS, self._flush_pending_seek)

    def _flush_pending_seek(self) -> bool:
        self._seek_pending_timer = 0
        if self._seek_target_ns >= 0:
            self._seek_to(self._seek_target_ns)
            self._seek_target_ns = -1
        return False

    def _flush_seek_on_track_change(self) -> bool:
        if not self._is_seekable():
            return False
        pos = self._query_position()
        try:
            self.playbin.seek(
                1.0,
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH,
                Gst.SeekType.SET,
                pos,
                Gst.SeekType.NONE,
                0,
            )
        except Exception:
            pass
        return False

    def _start_position_poll(self) -> None:
        self._stop_position_poll()
        self._position_timer = GLib.timeout_add(POSITION_POLL_MS, self._update_position)

    def _stop_position_poll(self) -> None:
        if self._position_timer:
            GLib.source_remove(self._position_timer)
            self._position_timer = 0

    def _update_position(self) -> bool:
        if self._current_title is None:
            return False
        if self._seeking:
            return True

        dur = self._query_duration()
        if dur <= 0:
            dur = self._duration_ns
        pos = self._query_position()
        if dur > 0:
            self._duration_ns = dur

        if self._pending_seek_display_ns >= 0:
            if pos <= 0 and self._pending_seek_display_ns > 0:
                if GLib.get_monotonic_time() < self._pending_seek_deadline_us:
                    pos = self._pending_seek_display_ns
                else:
                    self._pending_seek_display_ns = -1
                    self._pending_seek_deadline_us = 0
            else:
                self._pending_seek_display_ns = -1
                self._pending_seek_deadline_us = 0

        self._set_position_display(pos, dur if dur > 0 else None)

        self._update_stream_stats()

        return True

    # ── Seek events ──

    def _on_seek_start(self, _w: Gtk.Widget, _e: Gdk.EventButton) -> bool:
        self._seeking = True
        return False

    def _on_seek_end(self, _w: Gtk.Widget, _e: Gdk.EventButton) -> bool:
        dur = self._duration_ns or self._query_duration()
        if dur > 0:
            frac = self.seek_scale.get_value() / 1000
            target = int(frac * dur)
            self._seek_to(target)
        GLib.timeout_add(150, self._end_seeking)
        return False

    def _end_seeking(self) -> bool:
        self._seeking = False
        return False

    def _on_seek_value_changed(self, scale: Gtk.Scale) -> None:
        if not self._seeking:
            return
        dur = self._duration_ns or self._query_duration()
        if dur > 0:
            frac = scale.get_value() / 1000
            pos = int(frac * dur)
            self.time_current.set_text(_format_time(pos))
            if self._fs_time_current and self._fullscreen:
                self._fs_time_current.set_text(_format_time(pos))

    def _on_fs_seek_start(self, _w: Gtk.Widget, _e: Gdk.EventButton) -> bool:
        self._seeking = True
        return False

    def _on_fs_seek_end(self, _w: Gtk.Widget, _e: Gdk.EventButton) -> bool:
        dur = self._duration_ns or self._query_duration()
        if dur > 0 and self._fs_seek_scale:
            frac = self._fs_seek_scale.get_value() / 1000
            self._seek_to(int(frac * dur))
        GLib.timeout_add(150, self._end_seeking)
        return False

    def _on_fs_seek_value_changed(self, scale: Gtk.Scale) -> None:
        if not self._seeking:
            return
        dur = self._duration_ns or self._query_duration()
        if dur > 0:
            frac = scale.get_value() / 1000
            pos = int(frac * dur)
            if self._fs_time_current:
                self._fs_time_current.set_text(_format_time(pos))
            self.time_current.set_text(_format_time(pos))

    # ── Skip buttons ──

    def _on_skip_back(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None or not self._is_seekable():
            return
        pos = self._effective_position()
        self._seek_to(max(0, pos - SEEK_STEP_NS))

    def _on_skip_forward(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None or not self._is_seekable():
            return
        pos = self._effective_position()
        dur = self._duration_ns or self._query_duration()
        target = pos + SEEK_STEP_NS
        if dur > 0:
            target = min(target, dur - Gst.SECOND)
        self._seek_to(max(0, target))

    # ── Volume helpers ──

    def _vol_text(self) -> str:
        pct = int(round(self._volume * 100))
        return f"{pct}%"

    def _volume_icon_name(self) -> str:
        if self._volume <= 0.01:
            return "audio-volume-muted-symbolic"
        if self._volume < 0.34:
            return "audio-volume-low-symbolic"
        if self._volume < 0.67:
            return "audio-volume-medium-symbolic"
        return "audio-volume-high-symbolic"

    def _refresh_volume_widgets(self) -> None:
        vt = self._vol_text()
        self.vol_label.set_text(vt)
        if self._vol_icon is not None:
            self._vol_icon.set_from_icon_name(self._volume_icon_name(), Gtk.IconSize.MENU)
        if self._vol_button is not None:
            self._vol_button.set_tooltip_text(t("volume_control"))
        if hasattr(self, "_fs_vol_label"):
            self._fs_vol_label.set_text(vt)
        if self._fs_vol_icon is not None:
            self._fs_vol_icon.set_from_icon_name(self._volume_icon_name(), Gtk.IconSize.MENU)
        if self._fs_vol_button is not None:
            self._fs_vol_button.set_tooltip_text(t("volume_control"))
        if self._vol_popover_icon is not None:
            self._vol_popover_icon.set_from_icon_name(
                self._volume_icon_name(), Gtk.IconSize.MENU
            )
        if self._fs_vol_popover_icon is not None:
            self._fs_vol_popover_icon.set_from_icon_name(
                self._volume_icon_name(), Gtk.IconSize.MENU
            )
        if self._vol_popover_value is not None:
            self._vol_popover_value.set_text(vt)
        if self._fs_vol_popover_value is not None:
            self._fs_vol_popover_value.set_text(vt)
        self._sync_volume_scales()

    def _sync_volume_scales(self) -> None:
        value = int(round(self._volume * 100))
        self._ignore_volume_scale = True
        try:
            if self._vol_scale is not None:
                self._vol_scale.set_value(value)
            if self._fs_vol_scale is not None:
                self._fs_vol_scale.set_value(value)
        finally:
            self._ignore_volume_scale = False

    def _set_volume(self, volume: float, *, show_popup: bool = False) -> None:
        clamped = max(0.0, min(1.5, volume))
        self._volume = clamped
        if clamped > 0.01:
            self._last_nonzero_volume = clamped
        self.playbin.set_property("volume", self._volume)
        self._refresh_volume_widgets()
        if show_popup:
            self._show_vol_popup()

    def _toggle_mute(self) -> None:
        if self._volume <= 0.01:
            restored = self._last_nonzero_volume
            if restored <= 0.01:
                restored = max(0.05, get_settings().default_volume / 100)
            self._set_volume(restored, show_popup=True)
            return
        self._last_nonzero_volume = self._volume
        self._set_volume(0.0, show_popup=True)

    def _on_volume_scale_changed(self, scale: Gtk.Scale) -> None:
        if self._ignore_volume_scale:
            return
        self._set_volume(scale.get_value() / 100)

    def _toggle_volume_popover(self, button: Gtk.Button) -> None:
        popover = self._fs_vol_popover if button is self._fs_vol_button else self._vol_popover
        if popover is None:
            return
        if popover.get_visible():
            popover.hide()
            return
        if self._fs_vol_popover is not None and popover is not self._fs_vol_popover:
            self._fs_vol_popover.hide()
        if self._vol_popover is not None and popover is not self._vol_popover:
            self._vol_popover.hide()
        self._sync_volume_scales()
        popover.show_all()
        if self._fullscreen and self._fs_controls_revealer is not None:
            self._fs_controls_revealer.set_reveal_child(True)
            self._reset_fs_hide_timer()

    def _on_volume_chip_click(self, btn: Gtk.Button) -> None:
        self._toggle_volume_popover(btn)

    def _show_vol_popup(self) -> None:
        vt = self._vol_text()
        if self._fullscreen and hasattr(self, '_fs_vol_popup'):
            self._fs_vol_popup.set_text(vt)
            self._fs_vol_popup.show()
        else:
            self._vol_popup.set_text(vt)
            self._vol_popup.show()
        if self._vol_popup_timer:
            GLib.source_remove(self._vol_popup_timer)
        self._vol_popup_timer = GLib.timeout_add(1200, self._hide_vol_popup)

    def _hide_vol_popup(self) -> bool:
        self._vol_popup.hide()
        if hasattr(self, '_fs_vol_popup'):
            self._fs_vol_popup.hide()
        self._vol_popup_timer = 0
        return False

    # ── Events ──

    def _on_scroll(self, _w: Gtk.Widget, event: Gdk.EventScroll) -> bool:
        if self._current_title is None:
            return False
        _ok, dx, dy = event.get_scroll_deltas()
        if not _ok:
            if event.direction == Gdk.ScrollDirection.UP:
                dy = -1.0
            elif event.direction == Gdk.ScrollDirection.DOWN:
                dy = 1.0
            else:
                return False
        step = 0.05
        self._set_volume(self._volume + (-dy * step), show_popup=True)
        return True

    def _on_button_press(self, _w: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._show_context_menu(event)
            return True
        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS and event.button == 1:
            self._toggle_fullscreen()
            return True
        return False

    def _on_video_button_press(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if hasattr(widget, "get_can_focus") and widget.get_can_focus():
            widget.grab_focus()
        return self._on_button_press(widget, event)

    def _adjust_volume(self, delta: float) -> None:
        self._set_volume(self._volume + delta, show_popup=True)

    def _set_play_pause_icons(self, paused: bool) -> None:
        icon_name = (
            "media-playback-start-symbolic" if paused else "media-playback-pause-symbolic"
        )
        tooltip = t("resume") if paused else t("pause")
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        self.btn_play.set_image(image)
        self.btn_play.set_tooltip_text(tooltip)
        if self._fs_pp_btn is not None:
            self._fs_pp_btn.set_image(
                Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
            )
            self._fs_pp_btn.set_tooltip_text(tooltip)

    def _on_play_pause(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None:
            return
        if self._paused:
            self.playbin.set_state(Gst.State.PLAYING)
            self._paused = False
        else:
            self.playbin.set_state(Gst.State.PAUSED)
            self._paused = True
        self._set_play_pause_icons(self._paused)

    def _on_stop_click(self, _btn: Gtk.Button) -> None:
        self.stop()

    def _on_fs_click(self, _btn: Gtk.Button) -> None:
        self._toggle_fullscreen()

    def _on_prev_item_click(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None or self._on_prev_item is None:
            return
        self._on_prev_item()

    def _on_next_item_click(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None or self._on_next_item is None:
            return
        self._on_next_item()

    # ── Context menu ──

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        if self._paused:
            item_pp = Gtk.MenuItem(label=t("resume"))
        else:
            item_pp = Gtk.MenuItem(label=t("pause"))
        item_pp.connect("activate", lambda _: self._on_play_pause(None))
        menu.append(item_pp)

        item_stop = Gtk.MenuItem(label=t("stop"))
        item_stop.connect("activate", lambda _: self.stop())
        menu.append(item_stop)

        menu.append(Gtk.SeparatorMenuItem())

        # Audio tracks
        audio_sub = Gtk.Menu()
        audio_item = Gtk.MenuItem(label=t("audio_track"))
        audio_item.set_submenu(audio_sub)
        try:
            n_audio = int(self.playbin.get_property("n-audio"))
            cur_audio = int(self.playbin.get_property("current-audio"))
        except Exception:
            n_audio, cur_audio = 0, 0

        if n_audio > 0:
            for i in range(n_audio):
                label = self._audio_label(i)
                if i == cur_audio:
                    label += "  *"
                mi = Gtk.MenuItem(label=label)
                mi.connect("activate", self._set_audio_track, i)
                audio_sub.append(mi)
        else:
            mi = Gtk.MenuItem(label=t("no_audio"))
            mi.set_sensitive(False)
            audio_sub.append(mi)
        menu.append(audio_item)

        # Subtitle tracks
        sub_sub = Gtk.Menu()
        sub_item = Gtk.MenuItem(label=t("subtitle"))
        sub_item.set_submenu(sub_sub)
        try:
            n_text = int(self.playbin.get_property("n-text"))
            cur_text = int(self.playbin.get_property("current-text"))
        except Exception:
            n_text, cur_text = 0, -1

        off_mi = Gtk.MenuItem(label=t("subtitle_off") + ("  *" if cur_text < 0 else ""))
        off_mi.connect("activate", self._set_text_track, -1)
        sub_sub.append(off_mi)
        for i in range(n_text):
            label = self._text_label(i)
            if i == cur_text:
                label += "  *"
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", self._set_text_track, i)
            sub_sub.append(mi)
        menu.append(sub_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Color settings
        color_item = Gtk.MenuItem(label=t("color_settings"))
        color_item.connect("activate", lambda _: self._show_color_dialog())
        menu.append(color_item)

        menu.append(Gtk.SeparatorMenuItem())

        if self._fullscreen:
            fs_item = Gtk.MenuItem(label=t("exit_fullscreen"))
        else:
            fs_item = Gtk.MenuItem(label=t("fullscreen"))
        fs_item.connect("activate", lambda _: self._toggle_fullscreen())
        menu.append(fs_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _get_track_label(self, track_type: str, index: int) -> str:
        try:
            signal_name = f"get-{track_type}-tags"
            tags = self.playbin.emit(signal_name, index)
            if tags is None:
                return ""
        except Exception:
            return ""

        parts: list[str] = []

        ok, lang = tags.get_string("language-name")
        if ok and lang:
            parts.append(lang)
        else:
            ok, code = tags.get_string("language-code")
            if ok and code:
                parts.append(code.upper())

        ok, title = tags.get_string("title")
        if ok and title and title not in parts:
            parts.append(title)

        if not parts:
            ok, codec = tags.get_string("codec")
            if ok and codec:
                parts.append(codec)

        return " - ".join(parts)

    def _audio_label(self, index: int) -> str:
        name = self._get_track_label("audio", index)
        return name if name else t("audio_n", n=index + 1)

    def _text_label(self, index: int) -> str:
        name = self._get_track_label("text", index)
        return name if name else t("subtitle_n", n=index + 1)

    def _set_audio_track(self, _mi: Gtk.MenuItem, index: int) -> None:
        try:
            self.playbin.set_property("current-audio", index)
        except Exception:
            pass
        GLib.timeout_add(50, self._flush_seek_on_track_change)

    def _set_text_track(self, _mi: Gtk.MenuItem, index: int) -> None:
        try:
            self.playbin.set_property("current-text", index)
        except Exception:
            pass
        GLib.timeout_add(50, self._flush_seek_on_track_change)

    # ── Color settings ──

    def _apply_color_balance(self) -> None:
        vb = self._videobalance
        if not vb:
            return
        # videobalance properties:
        #   brightness: -1.0 .. 1.0 (default 0)
        #   contrast:    0.0 .. 2.0 (default 1)
        #   saturation:  0.0 .. 2.0 (default 1)
        #   hue:        -1.0 .. 1.0 (default 0)
        vb.set_property("brightness", self._brightness)
        vb.set_property("contrast", 1.0 + self._contrast)
        vb.set_property("saturation", 1.0 + self._saturation)
        vb.set_property("hue", self._hue)

    def _show_color_dialog(self) -> None:
        parent = self._fs_window if self._fullscreen else self.get_toplevel()
        dlg = Gtk.Dialog(
            title=t("color_settings"),
            transient_for=parent,
            modal=True,
            use_header_bar=True,
        )
        dlg.set_default_size(400, 0)
        dlg.add_button(t("reset"), Gtk.ResponseType.REJECT)
        dlg.add_button(t("close"), Gtk.ResponseType.CLOSE)

        content = dlg.get_content_area()
        content.set_border_width(16)
        content.set_spacing(12)

        sliders: dict[str, Gtk.Scale] = {}
        for key, label, val in [
            ("brightness", t("brightness"), self._brightness),
            ("contrast", t("contrast"), self._contrast),
            ("saturation", t("saturation"), self._saturation),
            ("hue", t("hue"), self._hue),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            lbl = Gtk.Label(label=label)
            lbl.set_xalign(0)
            lbl.set_size_request(100, -1)
            lbl.get_style_context().add_class("settings-label")
            row.pack_start(lbl, False, False, 0)

            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 1)
            scale.set_value(val * 100)
            scale.set_draw_value(True)
            scale.set_hexpand(True)
            scale.get_style_context().add_class("settings-scale")
            scale.connect("value-changed", self._on_color_changed, key)
            row.pack_start(scale, True, True, 0)

            content.pack_start(row, False, False, 0)
            sliders[key] = scale

        dlg.show_all()

        def on_response(_d: Gtk.Dialog, resp: int) -> None:
            if resp == Gtk.ResponseType.REJECT:
                self._brightness = 0.0
                self._contrast = 0.0
                self._saturation = 0.0
                self._hue = 0.0
                for k, s in sliders.items():
                    s.set_value(0)
                self._apply_color_balance()
                self._save_color_settings()
                return
            dlg.destroy()

        dlg.connect("response", on_response)

    def _on_color_changed(self, scale: Gtk.Scale, key: str) -> None:
        val = scale.get_value() / 100.0
        if key == "brightness":
            self._brightness = val
        elif key == "contrast":
            self._contrast = val
        elif key == "saturation":
            self._saturation = val
        elif key == "hue":
            self._hue = val
        self._apply_color_balance()
        self._save_color_settings()

    def _save_color_settings(self) -> None:
        settings = get_settings()
        settings.color_brightness = self._brightness
        settings.color_contrast = self._contrast
        settings.color_saturation = self._saturation
        settings.color_hue = self._hue
        save_settings(settings)

    # ── Fullscreen ──

    def _toggle_fullscreen(self) -> None:
        if self._current_title is None:
            return
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _ensure_fs_window(self) -> None:
        if self._fs_window is not None:
            return

        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_title(t("app_name"))
        win.connect("delete-event", self._on_fs_delete)
        win.connect("key-press-event", self._on_fs_key)
        if self._fs_accel_group is None:
            accel_group = Gtk.AccelGroup()
            accel_group.connect(
                Gdk.KEY_space,
                Gdk.ModifierType(0),
                Gtk.AccelFlags.VISIBLE,
                lambda *_args: self._activate_play_pause_accel(),
            )
            accel_group.connect(
                Gdk.KEY_KP_Space,
                Gdk.ModifierType(0),
                Gtk.AccelFlags.VISIBLE,
                lambda *_args: self._activate_play_pause_accel(),
            )
            self._fs_accel_group = accel_group
        win.add_accel_group(self._fs_accel_group)

        overlay = Gtk.Overlay()
        stage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stage.get_style_context().add_class("fs-stage")

        fs_event = Gtk.EventBox()
        fs_event.add_events(
            Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        fs_event.set_can_focus(True)
        fs_event.connect("scroll-event", self._on_scroll)
        fs_event.connect("button-press-event", self._on_video_button_press)
        fs_event.connect("key-press-event", self._on_fs_key)
        fs_event.connect("motion-notify-event", self._on_fs_motion)
        self._fs_event_box = fs_event

        self._fs_video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._fs_video_box.set_hexpand(True)
        self._fs_video_box.set_vexpand(True)
        fs_event.add(self._fs_video_box)
        stage.pack_start(fs_event, True, True, 0)
        overlay.add(stage)

        # Overlay controls with seek bar
        rev = Gtk.Revealer()
        rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        rev.set_transition_duration(250)
        rev.set_halign(Gtk.Align.FILL)
        rev.set_valign(Gtk.Align.END)

        controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        controls_box.get_style_context().add_class("fs-overlay-bar")

        # Fullscreen seek row
        fs_seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._fs_time_current = make_label("00:00", css="time-label-fs")
        fs_seek_row.pack_start(self._fs_time_current, False, False, 0)

        self._fs_seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self._fs_seek_scale.set_draw_value(False)
        self._fs_seek_scale.set_hexpand(True)
        self._fs_seek_scale.get_style_context().add_class("seek-slider-fs")
        self._fs_seek_scale.connect("button-press-event", self._on_fs_seek_start)
        self._fs_seek_scale.connect("button-release-event", self._on_fs_seek_end)
        self._fs_seek_scale.connect("value-changed", self._on_fs_seek_value_changed)
        fs_seek_row.pack_start(self._fs_seek_scale, True, True, 0)

        self._fs_time_total = make_label("00:00", css="time-label-fs")
        fs_seek_row.pack_start(self._fs_time_total, False, False, 0)
        controls_box.pack_start(fs_seek_row, False, False, 0)

        # Fullscreen button row
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        transport.get_style_context().add_class("ctrl-cluster")
        transport.get_style_context().add_class("ctrl-cluster-transport")
        bar.pack_start(transport, False, False, 0)

        btn_prev = make_icon_button(
            "media-skip-backward-symbolic", t("previous_content"), css="ctrl-btn-nav"
        )
        btn_prev.connect("clicked", self._on_prev_item_click)
        transport.pack_start(btn_prev, False, False, 0)

        btn_rew = make_icon_button(
            "media-seek-backward-symbolic",
            t("skip_back_short"),
            css="ctrl-btn-small",
            size=Gtk.IconSize.MENU,
        )
        btn_rew.connect("clicked", self._on_skip_back)
        transport.pack_start(btn_rew, False, False, 0)

        btn_pp = make_icon_button("media-playback-pause-symbolic", t("pause"), css="ctrl-btn")
        btn_pp.connect("clicked", self._on_play_pause)
        transport.pack_start(btn_pp, False, False, 0)
        self._fs_pp_btn = btn_pp

        btn_fwd = make_icon_button(
            "media-seek-forward-symbolic",
            t("skip_forward_short"),
            css="ctrl-btn-small",
            size=Gtk.IconSize.MENU,
        )
        btn_fwd.connect("clicked", self._on_skip_forward)
        transport.pack_start(btn_fwd, False, False, 0)

        btn_next = make_icon_button(
            "media-skip-forward-symbolic", t("next_content"), css="ctrl-btn-nav"
        )
        btn_next.connect("clicked", self._on_next_item_click)
        transport.pack_start(btn_next, False, False, 0)

        btn_stop = make_icon_button("media-playback-stop-symbolic", t("stop"), css="ctrl-btn")
        btn_stop.connect("clicked", self._on_stop_click)
        transport.pack_start(btn_stop, False, False, 0)

        self._fs_title = make_label("", css="fs-title", ellipsize=True)
        self._fs_title.get_style_context().add_class("ctrl-title-block")
        bar.pack_start(self._fs_title, True, True, 4)

        # Fullscreen stream stats
        fs_stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fs_stats.set_valign(Gtk.Align.CENTER)
        fs_stats.get_style_context().add_class("stats-cluster")
        self._fs_res_label = make_label("", css="stream-stat")
        self._fs_fps_label = make_label("", css="stream-stat")
        self._fs_bitrate_label = make_label("", css="stream-stat")
        fs_stats.pack_start(self._fs_res_label, False, False, 0)
        fs_stats.pack_start(self._fs_fps_label, False, False, 0)
        fs_stats.pack_start(self._fs_bitrate_label, False, False, 0)
        bar.pack_start(fs_stats, False, False, 4)

        utility = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        utility.get_style_context().add_class("ctrl-cluster")
        utility.get_style_context().add_class("ctrl-cluster-utility")
        bar.pack_start(utility, False, False, 0)

        fs_vol_button = Gtk.Button()
        fs_vol_button.get_style_context().add_class("vol-chip-btn")
        fs_vol_button.set_tooltip_text(t("volume_control"))
        fs_vol_button.connect("clicked", self._on_volume_chip_click)
        self._fs_vol_button = fs_vol_button

        fs_vol_chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fs_vol_chip.get_style_context().add_class("vol-chip")
        self._fs_vol_icon = Gtk.Image.new_from_icon_name(
            self._volume_icon_name(), Gtk.IconSize.MENU
        )
        self._fs_vol_icon.get_style_context().add_class("vol-chip-icon")
        fs_vol_chip.pack_start(self._fs_vol_icon, False, False, 0)
        fs_vol = make_label(self._vol_text(), css="vol-label")
        self._fs_vol_label = fs_vol
        fs_vol_chip.pack_start(fs_vol, False, False, 0)
        fs_vol_button.add(fs_vol_chip)
        utility.pack_start(fs_vol_button, False, False, 0)
        (
            self._fs_vol_popover,
            self._fs_vol_scale,
            self._fs_vol_popover_icon,
            self._fs_vol_popover_value,
        ) = self._build_volume_popover(fs_vol_button)

        btn_exit = make_icon_button(
            "view-restore-symbolic", t("exit_fullscreen"), css="ctrl-btn-utility"
        )
        btn_exit.connect("clicked", lambda _: self._exit_fullscreen())
        utility.pack_start(btn_exit, False, False, 0)

        controls_box.pack_start(bar, False, False, 0)
        rev.add(controls_box)
        overlay.add_overlay(rev)
        self._fs_controls_revealer = rev

        # Volume popup for fullscreen
        fs_vol_popup = make_label("", css="vol-popup")
        fs_vol_popup.set_halign(Gtk.Align.CENTER)
        fs_vol_popup.set_valign(Gtk.Align.CENTER)
        fs_vol_popup.set_no_show_all(True)
        overlay.add_overlay(fs_vol_popup)
        self._fs_vol_popup = fs_vol_popup

        win.add(overlay)
        self._fs_window = win

    def _enter_fullscreen(self) -> None:
        if self._current_title is None:
            return
        self._ensure_fs_window()
        if not self._fs_video_box or not self._fs_window:
            return

        self._video_shell.remove(self.video_widget)
        self._fs_video_box.pack_start(self.video_widget, True, True, 0)

        if self._fs_title:
            self._fs_title.set_text(self._current_title or "")
        if self._fs_controls_revealer:
            self._fs_controls_revealer.set_reveal_child(True)
            self._reset_fs_hide_timer()

        self._fs_window.show_all()
        self._fs_window.fullscreen()
        self._fs_window.present()
        self._fullscreen = True
        GLib.idle_add(self._grab_fs_focus)

        self.btn_fs.set_image(
            Gtk.Image.new_from_icon_name("view-restore-symbolic", Gtk.IconSize.BUTTON)
        )
        self.btn_fs.set_tooltip_text(t("exit_fullscreen"))

    def _exit_fullscreen(self) -> None:
        if not self._fs_window or not self._fs_video_box:
            return
        self._fs_video_box.remove(self.video_widget)
        self._video_shell.pack_start(self.video_widget, True, True, 0)
        self._video_shell.show_all()
        self._fs_window.unfullscreen()
        self._fs_window.hide()
        self._fullscreen = False
        GLib.idle_add(self._grab_inline_focus)

        self.btn_fs.set_image(
            Gtk.Image.new_from_icon_name("view-fullscreen-symbolic", Gtk.IconSize.BUTTON)
        )
        self.btn_fs.set_tooltip_text(t("fullscreen"))

        if self._fs_hide_timer:
            GLib.source_remove(self._fs_hide_timer)
            self._fs_hide_timer = 0

    def _on_fs_delete(self, _w: Gtk.Window, _e: Gdk.Event) -> bool:
        self._exit_fullscreen()
        return True

    def _grab_fs_focus(self) -> bool:
        if not self._fullscreen or not self._fs_window:
            return False
        target = None
        if self.video_widget is not None and self.video_widget.get_can_focus():
            target = self.video_widget
        elif self._fs_event_box is not None:
            target = self._fs_event_box
        if target is not None:
            self._fs_window.set_focus(target)
            target.grab_focus()
        return False

    def _activate_play_pause_accel(self) -> bool:
        self._on_play_pause(None)
        return True

    def _grab_inline_focus(self) -> bool:
        if self._fullscreen:
            return False
        target = None
        if self.video_widget is not None and hasattr(self.video_widget, "get_can_focus"):
            if self.video_widget.get_can_focus():
                target = self.video_widget
        if target is None:
            target = self._event_box
        if target is not None and hasattr(target, "grab_focus"):
            target.grab_focus()
        return False

    def _on_playback_key(self, _w: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape and self._fullscreen:
            self._exit_fullscreen()
            return True
        if event.keyval in (Gdk.KEY_F11, Gdk.KEY_f, Gdk.KEY_F):
            self._toggle_fullscreen()
            return True
        if event.keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self._toggle_mute()
            return True
        if event.keyval in (Gdk.KEY_space, Gdk.KEY_KP_Space):
            self._on_play_pause(None)
            return True
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self._on_skip_back(None)
            return True
        if event.keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            self._on_skip_forward(None)
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._adjust_volume(0.05)
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._adjust_volume(-0.05)
            return True
        return False

    def _on_fs_key(self, _w: Gtk.Window, event: Gdk.EventKey) -> bool:
        return self._on_playback_key(_w, event)

    def _on_fs_motion(self, _w: Gtk.Widget, _e: Gdk.EventMotion) -> bool:
        if self._fs_controls_revealer:
            self._fs_controls_revealer.set_reveal_child(True)
        self._reset_fs_hide_timer()
        return False

    def _reset_fs_hide_timer(self) -> None:
        if self._fs_hide_timer:
            GLib.source_remove(self._fs_hide_timer)
        self._fs_hide_timer = GLib.timeout_add(3500, self._hide_fs_controls)

    def _hide_fs_controls(self) -> bool:
        if self._fs_controls_revealer:
            self._fs_controls_revealer.set_reveal_child(False)
        self._fs_hide_timer = 0
        return False

    # ── GStreamer messages ──

    def _on_gst_msg(self, _bus: Gst.Bus, msg: Gst.Message) -> None:
        if msg.type == Gst.MessageType.ERROR:
            err, _dbg = msg.parse_error()
            self._stop_position_poll()
            self._set_controls_sensitive(False)
            self._clear_stream_stats()
            title = self._current_title or t("channel")
            self.playbin.set_state(Gst.State.NULL)
            self._current_title = None
            self._current_meta = None
            self._paused = False
            self._duration_ns = 0
            if self._fullscreen:
                self._exit_fullscreen()
            self.show_empty(
                t("channel_offline"),
                t("channel_offline_sub", title=title),
            )
            self.ctrl_title.set_text(t("channel_offline"))
            self.ctrl_meta.set_text(title)
            if self._on_error:
                self._on_error(str(err))
        elif msg.type == Gst.MessageType.EOS:
            self._stop_position_poll()
            self.btn_play.set_sensitive(False)
            self.btn_seek_back.set_sensitive(False)
            self.btn_seek_fwd.set_sensitive(False)
            if self._on_eos:
                self._on_eos()
        elif msg.type == Gst.MessageType.STATE_CHANGED and msg.src == self.playbin:
            _old, new, _pend = msg.parse_state_changed()
            if new == Gst.State.PLAYING:
                self._paused = False
                self._set_play_pause_icons(False)
                self._start_position_poll()

    # ── Public API ──

    def play(self, uri: str, title: str, meta: str) -> None:
        keep_fullscreen = self._fullscreen
        self._stop_position_poll()
        self.playbin.set_state(Gst.State.NULL)
        self.playbin.set_property("uri", uri)
        self.playbin.set_property("volume", self._volume)

        # Apply buffer settings
        settings = get_settings()
        buf_dur = BUFFER_DURATIONS.get(settings.buffer_mode, 3 * Gst.SECOND)
        self.playbin.set_property("buffer-duration", buf_dur)

        self.playbin.set_state(Gst.State.PLAYING)

        self._current_title = title
        self._current_meta = meta
        self._paused = False
        self._duration_ns = 0
        self._seeking = False
        self._pending_seek_display_ns = -1
        self._pending_seek_deadline_us = 0
        self._measured_fps_text = ""

        self.stack.set_visible_child_name("video")
        self.ctrl_title.set_text(title)
        self.ctrl_meta.set_text(meta)
        if self._fs_title is not None and keep_fullscreen:
            self._fs_title.set_text(title)
        self._set_play_pause_icons(False)
        self.seek_scale.set_value(0)
        self.time_current.set_text("00:00")
        self.time_total.set_text("00:00")
        if self._fs_time_current is not None:
            self._fs_time_current.set_text("00:00")
        if self._fs_time_total is not None:
            self._fs_time_total.set_text("00:00")
        self._set_controls_sensitive(True)
        self._start_position_poll()
        if keep_fullscreen:
            if self._fs_controls_revealer is not None:
                self._fs_controls_revealer.set_reveal_child(True)
                self._reset_fs_hide_timer()
            GLib.idle_add(self._grab_fs_focus)
        else:
            GLib.idle_add(self._grab_inline_focus)

    def stop(self) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
        self._stop_position_poll()
        self.playbin.set_state(Gst.State.NULL)
        self._current_title = None
        self._current_meta = None
        self._paused = False
        self._duration_ns = 0
        self._pending_seek_display_ns = -1
        self._pending_seek_deadline_us = 0
        self._set_play_pause_icons(True)
        self._set_controls_sensitive(False)
        self._clear_stream_stats()
        self.ctrl_title.set_text(t("app_name"))
        self.ctrl_meta.set_text(t("waiting_content"))
        self.seek_scale.set_value(0)
        self.time_current.set_text("00:00")
        self.time_total.set_text("00:00")
        self.show_empty(t("select_from_list"), t("select_from_list_sub"))

    def show_empty(self, title: str, sub: str, *, show_btn: bool = False) -> None:
        self.empty_title.set_text(title)
        self.empty_sub.set_text(sub)
        self.empty_btn.set_visible(show_btn)
        self.stack.set_visible_child_name("empty")

    def set_default_volume(self, vol: float) -> None:
        self._set_volume(vol)

    @property
    def is_playing(self) -> bool:
        return self._current_title is not None

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_title(self) -> str | None:
        return self._current_title

    def destroy_resources(self) -> None:
        self._stop_position_poll()
        if self._seek_pending_timer:
            GLib.source_remove(self._seek_pending_timer)
        if self._vol_popup_timer:
            GLib.source_remove(self._vol_popup_timer)
        if self._fs_hide_timer:
            GLib.source_remove(self._fs_hide_timer)
        if self._fs_window:
            self._fs_window.destroy()
        self._pending_seek_display_ns = -1
        self._pending_seek_deadline_us = 0
        self.playbin.set_state(Gst.State.NULL)
