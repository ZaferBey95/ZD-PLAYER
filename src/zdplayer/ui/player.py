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
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._on_error = on_error
        self._on_eos = on_eos

        self._current_title: str | None = None
        self._current_meta: str | None = None
        self._paused = False
        self._fullscreen = False
        self._volume = 0.75
        self._vol_popup_timer = 0
        self._track_gen = 0
        self._ignore_track = False

        # Seek state
        self._seeking = False
        self._duration_ns: int = 0
        self._position_timer = 0
        self._seek_pending_timer = 0
        self._seek_target_ns: int = -1

        # Color balance (range: -1.0 to 1.0, default 0.0)
        _s = get_settings()
        self._brightness = _s.color_brightness
        self._contrast = _s.color_contrast
        self._saturation = _s.color_saturation
        self._hue = _s.color_hue

        self._fs_window: Gtk.Window | None = None
        self._fs_video_box: Gtk.Box | None = None
        self._fs_controls_revealer: Gtk.Revealer | None = None
        self._fs_title: Gtk.Label | None = None
        self._fs_hide_timer = 0
        self._fs_seek_scale: Gtk.Scale | None = None
        self._fs_time_current: Gtk.Label | None = None
        self._fs_time_total: Gtk.Label | None = None

        self._init_gst()
        self._build()

    # ── GStreamer setup ──

    def _init_gst(self) -> None:
        self.playbin = Gst.ElementFactory.make("playbin", "player")
        self.video_sink = Gst.ElementFactory.make("gtksink", "vsink")
        if not self.playbin or not self.video_sink:
            raise RuntimeError("GStreamer player could not be created.")

        self._videobalance = Gst.ElementFactory.make("videobalance", "vbalance")
        self._build_video_pipeline()
        self._apply_color_balance()
        self.playbin.set_property("volume", self._volume)
        self.playbin.connect("source-setup", self._on_source_setup)
        self.video_widget = self.video_sink.props.widget
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
            self.playbin.set_property("video-sink", self.video_sink)
            return

        vbin = Gst.Bin.new("vsinkbin")
        for el in elements:
            vbin.add(el)
        vbin.add(self.video_sink)

        # Link chain: elements... -> video_sink
        chain = elements + [self.video_sink]
        for i in range(len(chain) - 1):
            chain[i].link(chain[i + 1])

        pad = chain[0].get_static_pad("sink")
        ghost = Gst.GhostPad.new("sink", pad)
        vbin.add_pad(ghost)

        self.playbin.set_property("video-sink", vbin)

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
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self._event_box.connect("scroll-event", self._on_scroll)
        self._event_box.connect("button-press-event", self._on_button_press)

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
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.get_style_context().add_class("control-bar")
        bar.set_margin_top(4)
        bar.set_margin_start(4)
        bar.set_margin_end(4)
        bar.set_margin_bottom(4)
        self.pack_start(bar, False, False, 0)

        self.btn_rew = make_icon_button(
            "media-seek-backward-symbolic", t("skip_back"), css="ctrl-btn",
        )
        self.btn_rew.connect("clicked", self._on_skip_back)
        bar.pack_start(self.btn_rew, False, False, 0)

        self.btn_play = make_icon_button(
            "media-playback-start-symbolic", t("play_pause"), css="ctrl-btn-accent",
        )
        self.btn_play.connect("clicked", self._on_play_pause)
        bar.pack_start(self.btn_play, False, False, 0)

        self.btn_fwd = make_icon_button(
            "media-seek-forward-symbolic", t("skip_forward"), css="ctrl-btn",
        )
        self.btn_fwd.connect("clicked", self._on_skip_forward)
        bar.pack_start(self.btn_fwd, False, False, 0)

        self.btn_stop = make_icon_button(
            "media-playback-stop-symbolic", t("stop"), css="ctrl-btn",
        )
        self.btn_stop.connect("clicked", self._on_stop_click)
        bar.pack_start(self.btn_stop, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(6)
        sep.set_margin_bottom(6)
        bar.pack_start(sep, False, False, 4)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.set_valign(Gtk.Align.CENTER)
        self.ctrl_title = make_label(t("app_name"), css="ctrl-title", ellipsize=True)
        self.ctrl_meta = make_label(t("waiting_content"), css="ctrl-meta", ellipsize=True)
        titles.pack_start(self.ctrl_title, False, False, 0)
        titles.pack_start(self.ctrl_meta, False, False, 0)
        bar.pack_start(titles, True, True, 0)

        # Stream stats
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stats_box.set_valign(Gtk.Align.CENTER)
        self._res_label = make_label("", css="stream-stat")
        self._fps_label = make_label("", css="stream-stat")
        self._bitrate_label = make_label("", css="stream-stat")
        stats_box.pack_start(self._res_label, False, False, 0)
        stats_box.pack_start(self._fps_label, False, False, 0)
        stats_box.pack_start(self._bitrate_label, False, False, 0)
        bar.pack_start(stats_box, False, False, 4)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep2.set_margin_top(6)
        sep2.set_margin_bottom(6)
        bar.pack_start(sep2, False, False, 2)

        self.vol_label = make_label(self._vol_text(), css="vol-label")
        bar.pack_start(self.vol_label, False, False, 4)

        self.btn_fs = make_icon_button(
            "view-fullscreen-symbolic", t("fullscreen"), css="ctrl-btn",
        )
        self.btn_fs.connect("clicked", self._on_fs_click)
        bar.pack_start(self.btn_fs, False, False, 0)

        self._set_controls_sensitive(False)

    def _set_controls_sensitive(self, on: bool) -> None:
        self.btn_play.set_sensitive(on)
        self.btn_stop.set_sensitive(on)
        self.btn_fs.set_sensitive(on)
        self.btn_rew.set_sensitive(on)
        self.btn_fwd.set_sensitive(on)
        self.seek_scale.set_sensitive(on)

    # ── Stream stats ──

    def _update_stream_stats(self) -> None:
        fps_text = ""
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
                        if ok and den > 0:
                            fps = num / den
                            fps_text = f"{fps:.0f} FPS"
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
        self._res_label.set_text("")
        self._fps_label.set_text("")
        self._bitrate_label.set_text("")
        if hasattr(self, '_fs_res_label'):
            self._fs_res_label.set_text("")
            self._fs_fps_label.set_text("")
            self._fs_bitrate_label.set_text("")

    # ── Time / seek helpers ──

    def _query_duration(self) -> int:
        ok, dur = self.playbin.query_duration(Gst.Format.TIME)
        return dur if ok and dur > 0 else 0

    def _query_position(self) -> int:
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        return pos if ok and pos >= 0 else 0

    def _is_seekable(self) -> bool:
        _, state, _ = self.playbin.get_state(0)
        return state in (Gst.State.PLAYING, Gst.State.PAUSED)

    def _seek_to(self, position_ns: int) -> None:
        if not self._is_seekable():
            return
        position_ns = max(0, position_ns)
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
        pos = self._query_position()
        self._duration_ns = dur

        self.time_current.set_text(_format_time(pos))
        self.time_total.set_text(_format_time(dur))

        if dur > 0:
            frac = (pos / dur) * 1000
            self.seek_scale.set_value(frac)
        else:
            self.seek_scale.set_value(0)

        self._update_stream_stats()

        if self._fs_seek_scale and self._fullscreen:
            if self._fs_time_current:
                self._fs_time_current.set_text(_format_time(pos))
            if self._fs_time_total:
                self._fs_time_total.set_text(_format_time(dur))
            if dur > 0:
                self._fs_seek_scale.set_value((pos / dur) * 1000)

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
        pos = self._query_position()
        self._seek_to(max(0, pos - SEEK_STEP_NS))

    def _on_skip_forward(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None or not self._is_seekable():
            return
        pos = self._query_position()
        dur = self._duration_ns or self._query_duration()
        target = pos + SEEK_STEP_NS
        if dur > 0:
            target = min(target, dur - Gst.SECOND)
        self._seek_to(max(0, target))

    # ── Volume helpers ──

    def _vol_text(self) -> str:
        pct = int(round(self._volume * 100))
        return f"{pct}%"

    def _show_vol_popup(self) -> None:
        vt = self._vol_text()
        if self._fullscreen and hasattr(self, '_fs_vol_popup'):
            self._fs_vol_popup.set_text(vt)
            self._fs_vol_popup.show()
            if hasattr(self, '_fs_vol_label'):
                self._fs_vol_label.set_text(vt)
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
        self._volume = max(0.0, min(1.5, self._volume + (-dy * step)))
        self.playbin.set_property("volume", self._volume)
        self.vol_label.set_text(self._vol_text())
        self._show_vol_popup()
        return True

    def _on_button_press(self, _w: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._show_context_menu(event)
            return True
        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS and event.button == 1:
            self._toggle_fullscreen()
            return True
        return False

    def _on_play_pause(self, _btn: Gtk.Button | None) -> None:
        if self._current_title is None:
            return
        if self._paused:
            self.playbin.set_state(Gst.State.PLAYING)
            self.btn_play.set_image(
                Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON)
            )
            self._paused = False
        else:
            self.playbin.set_state(Gst.State.PAUSED)
            self.btn_play.set_image(
                Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON)
            )
            self._paused = True

    def _on_stop_click(self, _btn: Gtk.Button) -> None:
        self.stop()

    def _on_fs_click(self, _btn: Gtk.Button) -> None:
        self._toggle_fullscreen()

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

        overlay = Gtk.Overlay()
        stage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stage.get_style_context().add_class("fs-stage")

        fs_event = Gtk.EventBox()
        fs_event.add_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        fs_event.connect("scroll-event", self._on_scroll)
        fs_event.connect("button-press-event", self._on_button_press)
        fs_event.connect("motion-notify-event", self._on_fs_motion)

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
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        btn_rew = make_icon_button("media-seek-backward-symbolic", t("skip_back_short"), css="ctrl-btn")
        btn_rew.connect("clicked", self._on_skip_back)
        bar.pack_start(btn_rew, False, False, 0)

        btn_pp = make_icon_button("media-playback-pause-symbolic", t("pause"), css="ctrl-btn")
        btn_pp.connect("clicked", self._on_play_pause)
        bar.pack_start(btn_pp, False, False, 0)
        self._fs_pp_btn = btn_pp

        btn_fwd = make_icon_button("media-seek-forward-symbolic", t("skip_forward_short"), css="ctrl-btn")
        btn_fwd.connect("clicked", self._on_skip_forward)
        bar.pack_start(btn_fwd, False, False, 0)

        btn_stop = make_icon_button("media-playback-stop-symbolic", t("stop"), css="ctrl-btn")
        btn_stop.connect("clicked", self._on_stop_click)
        bar.pack_start(btn_stop, False, False, 0)

        self._fs_title = make_label("", css="fs-title", ellipsize=True)
        bar.pack_start(self._fs_title, True, True, 4)

        # Fullscreen stream stats
        fs_stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fs_stats.set_valign(Gtk.Align.CENTER)
        self._fs_res_label = make_label("", css="stream-stat")
        self._fs_fps_label = make_label("", css="stream-stat")
        self._fs_bitrate_label = make_label("", css="stream-stat")
        fs_stats.pack_start(self._fs_res_label, False, False, 0)
        fs_stats.pack_start(self._fs_fps_label, False, False, 0)
        fs_stats.pack_start(self._fs_bitrate_label, False, False, 0)
        bar.pack_start(fs_stats, False, False, 4)

        fs_vol = make_label(self._vol_text(), css="vol-label")
        self._fs_vol_label = fs_vol
        bar.pack_start(fs_vol, False, False, 0)

        btn_exit = make_icon_button("view-restore-symbolic", t("exit_fullscreen"), css="ctrl-btn")
        btn_exit.connect("clicked", lambda _: self._exit_fullscreen())
        bar.pack_start(btn_exit, False, False, 0)

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

    def _on_fs_key(self, _w: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_F11):
            self._exit_fullscreen()
            return True
        if event.keyval == Gdk.KEY_space:
            self._on_play_pause(None)
            return True
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self._on_skip_back(None)
            return True
        if event.keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            self._on_skip_forward(None)
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._volume = min(1.5, self._volume + 0.05)
            self.playbin.set_property("volume", self._volume)
            self.vol_label.set_text(self._vol_text())
            if hasattr(self, '_fs_vol_label'):
                self._fs_vol_label.set_text(self._vol_text())
            self._show_vol_popup()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._volume = max(0.0, self._volume - 0.05)
            self.playbin.set_property("volume", self._volume)
            self.vol_label.set_text(self._vol_text())
            if hasattr(self, '_fs_vol_label'):
                self._fs_vol_label.set_text(self._vol_text())
            self._show_vol_popup()
            return True
        return False

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
            self.btn_rew.set_sensitive(False)
            self.btn_fwd.set_sensitive(False)
            if self._on_eos:
                self._on_eos()
        elif msg.type == Gst.MessageType.STATE_CHANGED and msg.src == self.playbin:
            _old, new, _pend = msg.parse_state_changed()
            if new == Gst.State.PLAYING:
                self.btn_play.set_image(
                    Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON)
                )
                self._paused = False
                self._start_position_poll()

    # ── Public API ──

    def play(self, uri: str, title: str, meta: str) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
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

        self.stack.set_visible_child_name("video")
        self.ctrl_title.set_text(title)
        self.ctrl_meta.set_text(meta)
        self.btn_play.set_image(
            Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.BUTTON)
        )
        self.seek_scale.set_value(0)
        self.time_current.set_text("00:00")
        self.time_total.set_text("00:00")
        self._set_controls_sensitive(True)
        self._start_position_poll()

    def stop(self) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
        self._stop_position_poll()
        self.playbin.set_state(Gst.State.NULL)
        self._current_title = None
        self._current_meta = None
        self._paused = False
        self._duration_ns = 0
        self.btn_play.set_image(
            Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        )
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
        self._volume = max(0.0, min(1.5, vol))
        self.playbin.set_property("volume", self._volume)
        self.vol_label.set_text(self._vol_text())

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
        self.playbin.set_state(Gst.State.NULL)
