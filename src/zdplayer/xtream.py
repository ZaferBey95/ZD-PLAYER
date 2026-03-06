from __future__ import annotations

from collections import OrderedDict

import requests
import urllib3

from .models import (
    AccountProfile,
    CatalogEntry,
    MediaCategory,
    SeriesInfo,
    XtreamAccount,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class XtreamError(RuntimeError):
    pass


class XtreamClient:
    timeout = 20
    user_agent = "ZD PLAYER"

    def _request(
        self,
        account: XtreamAccount,
        *,
        action: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> dict[str, object] | list[object]:
        params: dict[str, object] = {
            "username": account.username,
            "password": account.password,
        }
        if action:
            params["action"] = action
        if extra_params:
            params.update(extra_params)

        try:
            response = requests.get(
                account.api_url,
                params=params,
                timeout=self.timeout,
                verify=account.verify_tls,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise XtreamError(f"Xtream sunucusuna erisilemedi: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise XtreamError("Xtream sunucusu gecerli JSON donmedi.") from exc

        if isinstance(payload, dict):
            user_info = payload.get("user_info")
            user_info = user_info if isinstance(user_info, dict) else {}
            auth_value = str(user_info.get("auth", "1")).strip().lower()
            if auth_value in {"0", "false"}:
                raise XtreamError("Kullanici adi veya parola dogrulanamadi.")

        return payload

    def validate(self, account: XtreamAccount) -> AccountProfile:
        payload = self._request(account)
        if not isinstance(payload, dict):
            raise XtreamError("Kimlik dogrulama yaniti gecersiz.")
        return AccountProfile.from_api(payload, fallback_server=account.host_label)

    def fetch_catalog(
        self,
        account: XtreamAccount,
        content_type: str,
    ) -> tuple[AccountProfile, list[MediaCategory], list[CatalogEntry]]:
        profile = self.validate(account)

        categories_action = {
            "live": "get_live_categories",
            "movie": "get_vod_categories",
            "series": "get_series_categories",
        }.get(content_type)
        items_action = {
            "live": "get_live_streams",
            "movie": "get_vod_streams",
            "series": "get_series",
        }.get(content_type)

        if categories_action is None or items_action is None:
            raise XtreamError("Desteklenmeyen icerik tipi.")

        raw_categories = self._request(account, action=categories_action)
        raw_items = self._request(account, action=items_action)

        if not isinstance(raw_categories, list):
            raise XtreamError("Kategori yaniti beklenen formatta degil.")
        if not isinstance(raw_items, list):
            raise XtreamError("Icerik yaniti beklenen formatta degil.")

        categories: "OrderedDict[str, MediaCategory]" = OrderedDict()
        for item in raw_categories:
            if not isinstance(item, dict):
                continue
            category = MediaCategory.from_api(item, content_type)
            categories[category.id] = category

        entries: list[CatalogEntry] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                if content_type == "live":
                    entry = CatalogEntry.from_live_api(item)
                elif content_type == "movie":
                    entry = CatalogEntry.from_movie_api(item)
                else:
                    entry = CatalogEntry.from_series_api(item)
            except ValueError:
                continue
            entries.append(entry)
            if entry.category_id not in categories:
                categories[entry.category_id] = MediaCategory(
                    id=entry.category_id,
                    name="Diger",
                    content_type=content_type,
                )

        return profile, list(categories.values()), entries

    def fetch_series_info(
        self,
        account: XtreamAccount,
        series_id: str,
        *,
        fallback_name: str,
    ) -> SeriesInfo:
        payload = self._request(
            account,
            action="get_series_info",
            extra_params={"series_id": series_id},
        )
        if not isinstance(payload, dict):
            raise XtreamError("Dizi detay yaniti gecersiz.")
        return SeriesInfo.from_api(series_id, payload, fallback_name=fallback_name)
