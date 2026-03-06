from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .models import XtreamAccount


class StorageError(RuntimeError):
    pass


class AccountStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
        self.base_dir = base_dir or data_home / "zdplayer"
        self.state_file = self.base_dir / "state.json"
        self.legacy_base_dir = data_home / ("mint" + "iptv")
        self.legacy_state_file = self.legacy_base_dir / "state.json"

    def load(self) -> tuple[list[XtreamAccount], str | None]:
        if not self.state_file.exists() and self.legacy_state_file.exists():
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.legacy_state_file, self.state_file)
            except OSError:
                pass
        if not self.state_file.exists():
            return [], None

        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Kayitli hesaplar okunamadi: {exc}") from exc

        raw_accounts = payload.get("accounts", [])
        if not isinstance(raw_accounts, list):
            raise StorageError("Kayit dosyasi gecersiz.")

        accounts: list[XtreamAccount] = []
        for entry in raw_accounts:
            if isinstance(entry, dict):
                accounts.append(XtreamAccount.from_dict(entry))

        last_account_id = payload.get("last_account_id")
        if last_account_id is not None:
            last_account_id = str(last_account_id)

        return accounts, last_account_id

    def save(self, accounts: list[XtreamAccount], last_account_id: str | None) -> None:
        payload = {
            "last_account_id": last_account_id,
            "accounts": [account.to_dict() for account in accounts],
        }

        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError(f"Hesaplar kaydedilemedi: {exc}") from exc
