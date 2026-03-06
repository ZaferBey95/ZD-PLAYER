from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk

APP_CSS = """
/* ── Base ── */
window, dialog {
  background: #0d1117;
  color: #c9d1d9;
}

/* ── HeaderBar ── */
headerbar {
  background: #010409;
  border-bottom: 1px solid #21262d;
  box-shadow: none;
  min-height: 38px;
  padding: 0 8px;
}

headerbar *,
headerbar .title,
headerbar .subtitle {
  color: #c9d1d9;
}

headerbar button {
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  min-height: 28px;
  min-width: 28px;
  padding: 2px 8px;
}

headerbar button:hover {
  background: #21262d;
  border-color: #8b949e;
}

headerbar combobox button {
  background: #161b22;
}

/* ── Panels ── */
.panel {
  background: #161b22;
  border: none;
}

.panel-dark {
  background: #0d1117;
}

paned separator {
  background: #21262d;
  min-width: 2px;
  min-height: 2px;
}

/* ── Now-playing bar ── */
.now-playing {
  color: #58a6ff;
  font-size: 13px;
  font-weight: 700;
}

.now-meta {
  color: #8b949e;
  font-size: 11px;
}

/* ── Tab bar (segmented control) ── */
.tab-bar {
  background: #0d1117;
  padding: 6px 8px;
  border-bottom: 1px solid #21262d;
}

.tab-bar-inner {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 10px;
  padding: 3px;
}

.tab-btn {
  background: transparent;
  border: none;
  border-radius: 8px;
  color: #8b949e;
  font-size: 11px;
  font-weight: 700;
  padding: 6px 0;
  min-height: 0;
  letter-spacing: 0.3px;
}

.tab-btn:hover {
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.05);
}

.tab-btn-active {
  color: #ffffff;
  background: #1f6feb;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.tab-btn-active:hover {
  background: #388bfd;
}

/* ── Nav bar (back / breadcrumb) ── */
.nav-bar {
  background: #0d1117;
  border-bottom: 1px solid #21262d;
  padding: 6px 8px;
}

.nav-back-btn {
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #58a6ff;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 12px;
  min-height: 0;
  min-width: 0;
}

.nav-back-btn:hover {
  background: #161b22;
  border-color: #58a6ff;
}

.nav-title {
  color: #c9d1d9;
  font-size: 12px;
  font-weight: 700;
}

.nav-badge {
  background: #1f6feb;
  border-radius: 10px;
  padding: 1px 8px;
  color: #ffffff;
  font-size: 10px;
  font-weight: 700;
}

/* ── Info strip ── */
.info-strip {
  background: #161b22;
  border-bottom: 1px solid #21262d;
  padding: 4px 10px;
}

.info-strip-text {
  color: #484f58;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

/* ── Category bar (legacy, season combo etc.) ── */
.cat-bar {
  background: #0d1117;
  border-bottom: 1px solid #21262d;
  padding: 4px 6px;
}

.cat-bar combobox,
.cat-bar combobox button {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 4px;
  color: #c9d1d9;
  font-size: 12px;
  min-height: 26px;
}

/* ── Search ── */
.dark-search {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  padding: 4px 10px;
  font-size: 12px;
  min-height: 28px;
}

.dark-search:focus {
  border-color: #1f6feb;
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.2);
}

.dark-search image {
  color: #484f58;
}

/* ── Channel list (TreeView) ── */
.channel-list {
  background: #0d1117;
  color: #c9d1d9;
  font-size: 14px;
}

.channel-list header button {
  background: #161b22;
  border-bottom: 1px solid #21262d;
  color: #8b949e;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
}

.channel-list row,
.channel-list .cell {
  padding: 0;
}

.channel-list:selected,
.channel-list row:selected {
  background: #1f6feb;
  color: #ffffff;
}

.channel-list:hover {
  background: #161b22;
}

treeview.view {
  background: #0d1117;
  color: #c9d1d9;
  font-size: 14px;
}

treeview.view:selected {
  background: #1f6feb;
  color: #ffffff;
}

treeview.view:hover {
  background: #161b22;
}

treeview.view header button {
  background: #161b22;
  border: none;
  border-bottom: 1px solid #21262d;
  border-right: 1px solid #21262d;
  color: #8b949e;
  font-weight: 600;
  font-size: 11px;
  padding: 4px 8px;
}

/* ── Series back bar ── */
.series-bar {
  background: #161b22;
  border-bottom: 1px solid #21262d;
  padding: 6px 8px;
}

.series-bar button {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  padding: 2px 10px;
  font-size: 12px;
}

.series-bar button:hover {
  background: #30363d;
}

.series-name {
  color: #58a6ff;
  font-size: 13px;
  font-weight: 700;
}

.series-meta {
  color: #8b949e;
  font-size: 11px;
}

/* ── Player ── */
.video-area {
  background: #000000;
}

.player-empty-box {
  background: #0d1117;
}

.player-empty-title {
  color: #c9d1d9;
  font-size: 22px;
  font-weight: 800;
}

.player-empty-sub {
  color: #484f58;
  font-size: 13px;
}

/* ── Seek bar ── */
.seek-row {
  background: #161b22;
  padding: 2px 8px;
}

.time-label {
  color: #8b949e;
  font-size: 11px;
  font-weight: 600;
  min-width: 46px;
}

.time-label-fs {
  color: #c9d1d9;
  font-size: 11px;
  font-weight: 600;
  min-width: 46px;
}

scale.seek-slider trough {
  background: #30363d;
  border-radius: 999px;
  min-height: 5px;
}

scale.seek-slider highlight {
  background: #1f6feb;
  border-radius: 999px;
  min-height: 5px;
}

scale.seek-slider slider {
  background: #c9d1d9;
  border: 2px solid #1f6feb;
  border-radius: 999px;
  min-width: 14px;
  min-height: 14px;
  margin: -5px;
}

scale.seek-slider slider:hover {
  background: #ffffff;
}

scale.seek-slider-fs trough {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 999px;
  min-height: 5px;
}

scale.seek-slider-fs highlight {
  background: #58a6ff;
  border-radius: 999px;
  min-height: 5px;
}

scale.seek-slider-fs slider {
  background: #ffffff;
  border: 2px solid #58a6ff;
  border-radius: 999px;
  min-width: 12px;
  min-height: 12px;
  margin: -4px;
}

/* ── Control bar ── */
.control-bar {
  background: #161b22;
  border-top: 1px solid #21262d;
  padding: 4px 8px;
}

.ctrl-btn {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #c9d1d9;
  min-width: 34px;
  min-height: 34px;
  padding: 0;
}

.ctrl-btn:hover {
  background: #30363d;
  border-color: #8b949e;
}

.ctrl-btn-accent {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #ffffff;
}

.ctrl-btn-accent:hover {
  background: #388bfd;
  border-color: #388bfd;
}

.stream-stat {
  color: #3fb950;
  font-size: 10px;
  font-weight: 700;
}

.vol-label {
  color: #8b949e;
  font-size: 11px;
  font-weight: 700;
}

.vol-popup {
  background: rgba(13, 17, 23, 0.9);
  color: #c9d1d9;
  border-radius: 10px;
  padding: 10px 22px;
  font-size: 18px;
  font-weight: 800;
  border: 1px solid #30363d;
}

/* ── Fullscreen ── */
.fs-stage {
  background: #000000;
}

.fs-overlay-bar {
  background: rgba(1, 4, 9, 0.82);
  border-radius: 12px;
  padding: 8px 14px;
  margin: 14px;
  border: 1px solid rgba(48, 54, 61, 0.5);
}

.fs-title {
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 700;
}

/* ── Action buttons ── */
button.action-btn {
  background: #1f6feb;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 6px 16px;
  font-weight: 600;
}

button.action-btn:hover {
  background: #388bfd;
}

/* ── Info bar ── */
.info-label {
  color: #8b949e;
  font-size: 11px;
}

.count-label {
  color: #8b949e;
  font-size: 11px;
  font-weight: 700;
}

/* ── Dialogs ── */
dialog .dialog-vbox {
  background: #161b22;
}

/* ── Right-click menu ── */
menu {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 4px;
}

menu menuitem {
  color: #c9d1d9;
  border-radius: 4px;
  padding: 5px 12px;
  font-size: 12px;
}

menu menuitem:hover {
  background: #1f6feb;
  color: #ffffff;
}

menu separator {
  background: #21262d;
  margin: 3px 6px;
}

/* ── Scrollbar ── */
scrollbar {
  background: #0d1117;
}

scrollbar slider {
  background: #30363d;
  border-radius: 999px;
  min-width: 6px;
  min-height: 6px;
}

scrollbar slider:hover {
  background: #484f58;
}

/* ── Category list (ListBox) ── */
.cat-listbox {
  background: #0d1117;
}

.cat-listbox row {
  background: transparent;
  border-bottom: 1px solid #161b22;
  padding: 0;
  min-height: 0;
}

.cat-listbox row:hover {
  background: #161b22;
}

.cat-listbox row:selected {
  background: #1f6feb;
}

.cat-row-box {
  padding: 8px 12px;
}

.cat-row-name {
  color: #c9d1d9;
  font-size: 14px;
  font-weight: 600;
}

.cat-row-count {
  background: #21262d;
  border-radius: 10px;
  padding: 1px 8px;
  color: #8b949e;
  font-size: 10px;
  font-weight: 700;
  min-width: 20px;
}

.cat-row-arrow {
  color: #484f58;
  font-size: 11px;
}

.cat-listbox row:selected .cat-row-name,
.cat-listbox row:selected .cat-row-count,
.cat-listbox row:selected .cat-row-arrow {
  color: #ffffff;
}

.cat-listbox row:selected .cat-row-count {
  background: rgba(255, 255, 255, 0.2);
}

/* ── Dialog fields ── */
.dlg-entry {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  padding: 6px 10px;
  font-size: 13px;
  min-height: 32px;
}

.dlg-entry:focus {
  border-color: #1f6feb;
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.2);
}

.dlg-field-label {
  color: #8b949e;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.dlg-error {
  color: #f85149;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 0;
}

/* ── Dialog account list ── */
.dlg-account-list {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 8px;
}

.dlg-account-list row {
  background: transparent;
  border-bottom: 1px solid #161b22;
}

.dlg-account-list row:hover {
  background: #161b22;
}

.dlg-account-list row:selected {
  background: #1f6feb;
}

.dlg-avatar {
  background: #1f6feb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 800;
  border-radius: 999px;
}

.dlg-account-name {
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 700;
}

.dlg-account-detail {
  color: #8b949e;
  font-size: 11px;
}

.dlg-account-list row:selected .dlg-account-name,
.dlg-account-list row:selected .dlg-account-detail,
.dlg-account-list row:selected .dlg-avatar {
  color: #ffffff;
}

.dlg-account-list row:selected .dlg-avatar {
  background: rgba(255, 255, 255, 0.25);
}

/* ── Dialog action buttons ── */
button.dlg-action-secondary {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  padding: 6px 14px;
  font-weight: 600;
}

button.dlg-action-secondary:hover {
  background: #30363d;
  border-color: #8b949e;
}

button.dlg-action-danger {
  background: transparent;
  border: 1px solid #da3633;
  border-radius: 6px;
  color: #da3633;
  padding: 6px 14px;
  font-weight: 600;
}

button.dlg-action-danger:hover {
  background: #da3633;
  color: #ffffff;
}

/* ── Settings dialog ── */
.settings-section {
  color: #58a6ff;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.3px;
}

.settings-row {
  padding: 6px 0;
}

.settings-label {
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 600;
}

.settings-desc {
  color: #8b949e;
  font-size: 11px;
}

.settings-notice {
  color: #d29922;
  font-size: 12px;
  font-weight: 600;
}

.settings-scale trough {
  background: #30363d;
  border-radius: 999px;
  min-height: 5px;
}

.settings-scale highlight {
  background: #1f6feb;
  border-radius: 999px;
  min-height: 5px;
}

.settings-scale slider {
  background: #c9d1d9;
  border: 2px solid #1f6feb;
  border-radius: 999px;
  min-width: 14px;
  min-height: 14px;
  margin: -5px;
}

.settings-scale value {
  color: #8b949e;
  font-size: 11px;
}

/* ── Combobox global ── */
combobox button {
  background: #0d1117;
  color: #c9d1d9;
  border: 1px solid #30363d;
}

combobox button:hover {
  background: #161b22;
  border-color: #8b949e;
}

combobox cellview {
  background: transparent;
  color: #c9d1d9;
}

combobox arrow {
  color: #8b949e;
}

combobox window.popup,
combobox window.popup decoration {
  background: #161b22;
  border: 1px solid #30363d;
}

combobox window.popup menu,
combobox window.popup treeview.view {
  background: #161b22;
  color: #c9d1d9;
}

combobox window.popup menu menuitem {
  color: #c9d1d9;
}

combobox window.popup menu menuitem:hover,
combobox window.popup treeview.view:hover {
  background: #1f6feb;
  color: #ffffff;
}

combobox window.popup treeview.view:selected {
  background: #1f6feb;
  color: #ffffff;
}

/* ── Misc ── */
.dim-text {
  color: #484f58;
  font-size: 11px;
}

.card-title {
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 700;
}

.pill {
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 700;
}

.pill-active {
  background: #238636;
  color: #ffffff;
}

.pill-danger {
  background: #da3633;
  color: #ffffff;
}
"""


def install_css() -> None:
    screen = Gdk.Screen.get_default()
    if screen is None:
        return

    provider = Gtk.CssProvider()
    provider.load_from_data(APP_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        screen,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
