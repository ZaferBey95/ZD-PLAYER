from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    language: str = "tr"
    live_output: str = "ts"
    verify_tls: bool = True
    default_volume: int = 75
    buffer_mode: str = "normal"
    deinterlace: str = "auto"
    start_maximized: bool = False
    remember_last_channel: bool = False
    last_channel_id: str = ""
    last_channel_type: str = ""
    last_account_id: str = ""
    color_brightness: float = 0.0
    color_contrast: float = 0.0
    color_saturation: float = 0.0
    color_hue: float = 0.0


_data_home = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
)
_settings_dir = _data_home / "zdplayer"
_settings_file = _settings_dir / "settings.json"
_legacy_settings_dir = _data_home / ("mint" + "iptv")
_legacy_settings_file = _legacy_settings_dir / "settings.json"

_current = AppSettings()


def load_settings() -> AppSettings:
    global _current
    if not _settings_file.exists() and _legacy_settings_file.exists():
        try:
            _settings_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_legacy_settings_file, _settings_file)
        except OSError:
            pass
    if _settings_file.exists():
        try:
            data = json.loads(_settings_file.read_text(encoding="utf-8"))
            _current = AppSettings(
                language=str(data.get("language", "tr")),
                live_output=str(data.get("live_output", "ts")),
                verify_tls=bool(data.get("verify_tls", True)),
                default_volume=int(data.get("default_volume", 75)),
                buffer_mode=str(data.get("buffer_mode", "normal")),
                deinterlace=str(data.get("deinterlace", "auto")),
                start_maximized=bool(data.get("start_maximized", False)),
                remember_last_channel=bool(data.get("remember_last_channel", False)),
                last_channel_id=str(data.get("last_channel_id", "")),
                last_channel_type=str(data.get("last_channel_type", "")),
                last_account_id=str(data.get("last_account_id", "")),
                color_brightness=float(data.get("color_brightness", 0.0)),
                color_contrast=float(data.get("color_contrast", 0.0)),
                color_saturation=float(data.get("color_saturation", 0.0)),
                color_hue=float(data.get("color_hue", 0.0)),
            )
        except (OSError, json.JSONDecodeError, ValueError):
            _current = AppSettings()
    return _current


def save_settings(settings: AppSettings) -> None:
    global _current
    _current = settings
    try:
        _settings_dir.mkdir(parents=True, exist_ok=True)
        _settings_file.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def get_settings() -> AppSettings:
    return _current
