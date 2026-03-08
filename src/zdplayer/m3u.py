from __future__ import annotations

import re

import requests

from .models import CatalogEntry, MediaCategory


class M3UError(RuntimeError):
    pass


_EXTINF_RE = re.compile(
    r'#EXTINF:\s*-?\d+\s*(.*?)\s*,\s*(.*)\s*$'
)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _parse_extinf_attrs(raw: str) -> dict[str, str]:
    return dict(_ATTR_RE.findall(raw))


def fetch_and_parse(
    url: str,
    *,
    timeout: int = 30,
    verify_tls: bool = True,
) -> tuple[list[MediaCategory], list[CatalogEntry]]:
    try:
        resp = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "ZD PLAYER"},
            verify=verify_tls,
        )
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException as exc:
        raise M3UError(f"M3U listesi indirilemedi: {exc}") from exc

    if not text.strip().startswith("#EXTM3U"):
        raise M3UError("Geçersiz M3U formatı.")

    categories: dict[str, MediaCategory] = {}
    entries: list[CatalogEntry] = []
    entry_id = 0

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            m = _EXTINF_RE.match(line)
            if m:
                attrs_raw, name = m.group(1), m.group(2)
                attrs = _parse_extinf_attrs(attrs_raw)

                # Find the URL line
                url_line = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and not candidate.startswith("#"):
                        url_line = candidate
                        i = j
                        break

                if url_line:
                    entry_id += 1
                    group = attrs.get("group-title", "").strip()
                    cat_id = group or "uncategorized"
                    tvg_logo = attrs.get("tvg-logo", "")

                    if cat_id not in categories and cat_id != "uncategorized":
                        categories[cat_id] = MediaCategory(
                            id=cat_id,
                            name=group,
                            content_type="live",
                        )

                    entries.append(CatalogEntry(
                        id=str(entry_id),
                        name=name.strip() or f"Channel {entry_id}",
                        content_type="live",
                        category_id=cat_id,
                        icon_url=tvg_logo or None,
                        source_url=url_line,
                        number=entry_id,
                    ))
        i += 1

    if not entries:
        raise M3UError("M3U listesinde kanal bulunamadı.")

    if "uncategorized" in {e.category_id for e in entries} and "uncategorized" not in categories:
        categories["uncategorized"] = MediaCategory(
            id="uncategorized", name="Diğer", content_type="live",
        )

    return list(categories.values()), entries
