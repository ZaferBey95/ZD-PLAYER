from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

CONTENT_LABELS = {
    "live": "Canli TV",
    "movie": "Filmler",
    "series": "Diziler",
}


def _clean_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _timestamp_to_text(value: object) -> str | None:
    raw = _clean_text(value)
    if not raw or raw == "0":
        return None

    try:
        return datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return None


def _coerce_int(value: object) -> int | None:
    raw = _clean_text(value)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _coerce_float_text(value: object) -> str | None:
    raw = _clean_text(value)
    if not raw:
        return None
    try:
        number = float(raw)
    except ValueError:
        return raw or None
    return f"{number:.1f}"


def _is_direct_media_uri(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    return bool(parsed.scheme)


@dataclass(slots=True)
class XtreamAccount:
    id: str
    name: str
    server: str
    username: str
    password: str
    output: str = "ts"
    verify_tls: bool = True
    account_type: str = "xtream"  # "xtream" or "m3u"
    m3u_url: str = ""

    @classmethod
    def create(
        cls,
        *,
        name: str,
        server: str = "",
        username: str = "",
        password: str = "",
        output: str = "ts",
        verify_tls: bool = True,
        account_type: str = "xtream",
        m3u_url: str = "",
    ) -> "XtreamAccount":
        return cls(
            id=str(uuid4()),
            name=name.strip(),
            server=server.strip(),
            username=username.strip(),
            password=password,
            output=output,
            verify_tls=verify_tls,
            account_type=account_type,
            m3u_url=m3u_url.strip(),
        )

    @property
    def normalized_server(self) -> str:
        value = self.server.strip()
        if not value:
            raise ValueError("Sunucu adresi bos olamaz.")

        if "://" not in value:
            value = f"http://{value}"

        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Sunucu adresi gecersiz.")

        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    @property
    def api_url(self) -> str:
        return f"{self.normalized_server}/player_api.php"

    @property
    def host_label(self) -> str:
        parsed = urlparse(self.normalized_server)
        return parsed.netloc or self.normalized_server

    def build_stream_url(self, path_kind: str, item_id: str, extension: str) -> str:
        safe_id = str(item_id).strip()
        safe_ext = str(extension).strip().lstrip(".")
        if not safe_id:
            raise ValueError("Akis kimligi bos olamaz.")
        if not safe_ext:
            raise ValueError("Icerik uzantisi bos olamaz.")
        return (
            f"{self.normalized_server}/{path_kind}/"
            f"{self.username}/{self.password}/{safe_id}.{safe_ext}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "server": self.server,
            "username": self.username,
            "password": self.password,
            "output": self.output,
            "verify_tls": self.verify_tls,
            "account_type": self.account_type,
            "m3u_url": self.m3u_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "XtreamAccount":
        return cls(
            id=_clean_text(data.get("id")) or str(uuid4()),
            name=_clean_text(data.get("name")),
            server=_clean_text(data.get("server")),
            username=_clean_text(data.get("username")),
            password=_clean_text(data.get("password")),
            output=_clean_text(data.get("output"), "ts") or "ts",
            verify_tls=bool(data.get("verify_tls", True)),
            account_type=_clean_text(data.get("account_type"), "xtream") or "xtream",
            m3u_url=_clean_text(data.get("m3u_url")),
        )


@dataclass(slots=True)
class MediaCategory:
    id: str
    name: str
    content_type: str
    parent_id: str = "0"

    @classmethod
    def from_api(cls, payload: dict[str, object], content_type: str) -> "MediaCategory":
        category_id = _clean_text(payload.get("category_id"), "uncategorized")
        name = _clean_text(payload.get("category_name"), "Adsiz kategori")
        parent_id = _clean_text(payload.get("parent_id"), "0")
        return cls(
            id=category_id or "uncategorized",
            name=name,
            content_type=content_type,
            parent_id=parent_id,
        )


@dataclass(slots=True)
class CatalogEntry:
    id: str
    name: str
    content_type: str
    category_id: str
    icon_url: str | None = None
    plot: str | None = None
    rating: str | None = None
    year: str | None = None
    added_at: str | None = None
    duration: str | None = None
    epg_channel_id: str | None = None
    container_extension: str | None = None
    source_url: str | None = None
    number: int | None = None
    is_series_container: bool = False

    @classmethod
    def from_live_api(cls, payload: dict[str, object]) -> "CatalogEntry":
        stream_id = _clean_text(payload.get("stream_id"))
        if not stream_id:
            raise ValueError("Live stream kaydinda stream_id yok.")

        return cls(
            id=stream_id,
            name=_clean_text(payload.get("name"), "Adsiz kanal"),
            content_type="live",
            category_id=_clean_text(payload.get("category_id"), "uncategorized")
            or "uncategorized",
            icon_url=_clean_text(payload.get("stream_icon")) or None,
            plot=_clean_text(payload.get("plot")) or None,
            rating=_coerce_float_text(payload.get("rating")),
            epg_channel_id=_clean_text(payload.get("epg_channel_id")) or None,
            source_url=_clean_text(payload.get("source")) or None,
            number=_coerce_int(payload.get("num")),
        )

    @classmethod
    def from_movie_api(cls, payload: dict[str, object]) -> "CatalogEntry":
        stream_id = _clean_text(payload.get("stream_id"))
        if not stream_id:
            raise ValueError("Film kaydinda stream_id yok.")

        return cls(
            id=stream_id,
            name=_clean_text(payload.get("name"), "Adsiz film"),
            content_type="movie",
            category_id=_clean_text(payload.get("category_id"), "uncategorized")
            or "uncategorized",
            icon_url=_clean_text(payload.get("stream_icon")) or None,
            plot=_clean_text(payload.get("plot")) or None,
            rating=_coerce_float_text(payload.get("rating") or payload.get("rating_5based")),
            year=_clean_text(payload.get("year")) or None,
            added_at=_timestamp_to_text(payload.get("added")),
            duration=_clean_text(payload.get("duration")) or None,
            container_extension=_clean_text(payload.get("container_extension"), "mp4")
            or "mp4",
            source_url=_clean_text(payload.get("source")) or None,
        )

    @classmethod
    def from_series_api(cls, payload: dict[str, object]) -> "CatalogEntry":
        series_id = _clean_text(payload.get("series_id"))
        if not series_id:
            raise ValueError("Dizi kaydinda series_id yok.")

        return cls(
            id=series_id,
            name=_clean_text(payload.get("name"), "Adsiz dizi"),
            content_type="series",
            category_id=_clean_text(payload.get("category_id"), "uncategorized")
            or "uncategorized",
            icon_url=_clean_text(payload.get("cover")) or None,
            plot=_clean_text(payload.get("plot")) or None,
            rating=_coerce_float_text(payload.get("rating")),
            year=_clean_text(payload.get("releaseDate")) or _clean_text(payload.get("year")) or None,
            added_at=_timestamp_to_text(payload.get("last_modified")),
            is_series_container=True,
        )

    @property
    def search_blob(self) -> str:
        parts = [
            self.name,
            self.plot or "",
            self.rating or "",
            self.year or "",
            self.epg_channel_id or "",
        ]
        return " ".join(part.lower() for part in parts if part)

    @property
    def meta_line(self) -> str:
        parts: list[str] = []
        if self.content_type == "live" and self.number is not None:
            parts.append(f"No {self.number}")
        if self.year:
            parts.append(self.year)
        if self.duration:
            parts.append(self.duration)
        if self.rating:
            parts.append(f"IMDB {self.rating}")
        if self.epg_channel_id:
            parts.append(self.epg_channel_id)
        return " - ".join(parts)

    @property
    def detail_summary(self) -> str:
        return self.plot or self.meta_line or CONTENT_LABELS.get(self.content_type, self.content_type)

    def playback_url(self, account: XtreamAccount) -> str:
        if self.is_series_container:
            raise ValueError("Dizi kaydinin once sezon ve bolumu secilmeli.")

        if _is_direct_media_uri(self.source_url):
            return self.source_url

        if self.content_type == "live":
            return account.build_stream_url("live", self.id, account.output)

        if self.content_type == "movie":
            return account.build_stream_url(
                "movie",
                self.id,
                self.container_extension or "mp4",
            )

        if self.content_type == "series":
            return account.build_stream_url(
                "series",
                self.id,
                self.container_extension or "mp4",
            )

        raise ValueError("Bilinmeyen icerik tipi.")


@dataclass(slots=True)
class SeriesSeason:
    id: str
    season_number: str
    name: str
    air_date: str | None = None
    cover_url: str | None = None
    episode_count: int = 0


@dataclass(slots=True)
class SeriesEpisode:
    id: str
    series_id: str
    title: str
    season_number: str
    episode_number: int | None = None
    plot: str | None = None
    duration: str | None = None
    rating: str | None = None
    container_extension: str | None = None
    added_at: str | None = None
    source_url: str | None = None
    icon_url: str | None = None

    @classmethod
    def from_api(
        cls,
        series_id: str,
        season_number: str,
        payload: dict[str, object],
    ) -> "SeriesEpisode":
        episode_info = payload.get("info")
        episode_info = episode_info if isinstance(episode_info, dict) else {}

        episode_id = _clean_text(payload.get("id")) or _clean_text(payload.get("episode_id"))
        if not episode_id:
            raise ValueError("Bolum kaydinda id yok.")

        title = (
            _clean_text(payload.get("title"))
            or _clean_text(payload.get("name"))
            or _clean_text(episode_info.get("movie_image"))
            or f"Bolum {episode_id}"
        )

        return cls(
            id=episode_id,
            series_id=series_id,
            title=title,
            season_number=season_number,
            episode_number=_coerce_int(payload.get("episode_num")),
            plot=_clean_text(episode_info.get("plot")) or _clean_text(payload.get("plot")) or None,
            duration=_clean_text(episode_info.get("duration")) or _clean_text(payload.get("duration")) or None,
            rating=_coerce_float_text(episode_info.get("rating")) or _coerce_float_text(payload.get("rating")),
            container_extension=(
                _clean_text(payload.get("container_extension"))
                or _clean_text(episode_info.get("container_extension"))
                or "mp4"
            ),
            added_at=_timestamp_to_text(payload.get("added")),
            source_url=_clean_text(payload.get("source")) or None,
            icon_url=_clean_text(episode_info.get("movie_image")) or None,
        )

    @property
    def search_blob(self) -> str:
        parts = [
            self.title,
            self.plot or "",
            self.duration or "",
            self.rating or "",
            self.season_number,
            str(self.episode_number or ""),
        ]
        return " ".join(part.lower() for part in parts if part)

    @property
    def meta_line(self) -> str:
        parts = [f"Sezon {self.season_number}"]
        if self.episode_number is not None:
            parts.append(f"Bolum {self.episode_number}")
        if self.duration:
            parts.append(self.duration)
        if self.rating:
            parts.append(f"IMDB {self.rating}")
        return " - ".join(parts)

    def playback_url(self, account: XtreamAccount) -> str:
        if _is_direct_media_uri(self.source_url):
            return self.source_url
        return account.build_stream_url(
            "series",
            self.id,
            self.container_extension or "mp4",
        )


@dataclass(slots=True)
class SeriesInfo:
    id: str
    name: str
    plot: str | None = None
    cover_url: str | None = None
    cast: str | None = None
    director: str | None = None
    genre: str | None = None
    release_date: str | None = None
    rating: str | None = None
    seasons: list[SeriesSeason] = field(default_factory=list)
    episodes_by_season: dict[str, list[SeriesEpisode]] = field(default_factory=dict)

    @classmethod
    def from_api(
        cls,
        series_id: str,
        payload: dict[str, object],
        *,
        fallback_name: str,
    ) -> "SeriesInfo":
        info = payload.get("info")
        info = info if isinstance(info, dict) else {}

        raw_seasons = payload.get("seasons")
        raw_seasons = raw_seasons if isinstance(raw_seasons, list) else []
        raw_episodes = payload.get("episodes")
        raw_episodes = raw_episodes if isinstance(raw_episodes, dict) else {}

        seasons: list[SeriesSeason] = []
        for raw_season in raw_seasons:
            if not isinstance(raw_season, dict):
                continue
            season_number = (
                _clean_text(raw_season.get("season_number"))
                or _clean_text(raw_season.get("season"))
                or _clean_text(raw_season.get("season_num"))
            )
            if not season_number:
                continue
            seasons.append(
                SeriesSeason(
                    id=_clean_text(raw_season.get("id")) or season_number,
                    season_number=season_number,
                    name=_clean_text(raw_season.get("name")) or f"Sezon {season_number}",
                    air_date=_clean_text(raw_season.get("air_date")) or None,
                    cover_url=_clean_text(raw_season.get("cover")) or None,
                )
            )

        episodes_by_season: dict[str, list[SeriesEpisode]] = {}
        for season_number, entries in raw_episodes.items():
            if not isinstance(entries, list):
                continue
            season_key = _clean_text(season_number)
            season_episodes: list[SeriesEpisode] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    season_episodes.append(
                        SeriesEpisode.from_api(series_id, season_key, entry)
                    )
                except ValueError:
                    continue
            episodes_by_season[season_key] = season_episodes

        season_map = {season.season_number: season for season in seasons}
        for season_number, season_episodes in episodes_by_season.items():
            if season_number not in season_map:
                season = SeriesSeason(
                    id=season_number,
                    season_number=season_number,
                    name=f"Sezon {season_number}",
                )
                season_map[season_number] = season
                seasons.append(season)
            season_map[season_number].episode_count = len(season_episodes)

        return cls(
            id=series_id,
            name=_clean_text(info.get("name")) or fallback_name,
            plot=_clean_text(info.get("plot")) or None,
            cover_url=_clean_text(info.get("cover")) or None,
            cast=_clean_text(info.get("cast")) or None,
            director=_clean_text(info.get("director")) or None,
            genre=_clean_text(info.get("genre")) or None,
            release_date=_clean_text(info.get("releaseDate")) or None,
            rating=_coerce_float_text(info.get("rating")),
            seasons=seasons,
            episodes_by_season=episodes_by_season,
        )

    def find_episode(self, episode_id: str) -> SeriesEpisode | None:
        for episodes in self.episodes_by_season.values():
            for episode in episodes:
                if episode.id == episode_id:
                    return episode
        return None


@dataclass(slots=True)
class AccountProfile:
    account_status: str
    active_connections: int | None = None
    max_connections: int | None = None
    expires_at: str | None = None
    server_time: str | None = None
    server_url: str | None = None

    @classmethod
    def from_api(
        cls, payload: dict[str, object], *, fallback_server: str
    ) -> "AccountProfile":
        user_info = payload.get("user_info")
        server_info = payload.get("server_info")
        user_info = user_info if isinstance(user_info, dict) else {}
        server_info = server_info if isinstance(server_info, dict) else {}

        status = _clean_text(user_info.get("status"), "Unknown")
        active_raw = _clean_text(user_info.get("active_cons"))
        max_raw = _clean_text(user_info.get("max_connections"))

        try:
            active_connections = int(active_raw) if active_raw else None
        except ValueError:
            active_connections = None

        try:
            max_connections = int(max_raw) if max_raw else None
        except ValueError:
            max_connections = None

        return cls(
            account_status=status,
            active_connections=active_connections,
            max_connections=max_connections,
            expires_at=_timestamp_to_text(user_info.get("exp_date")),
            server_time=_clean_text(server_info.get("time_now")) or None,
            server_url=_clean_text(server_info.get("url")) or fallback_server,
        )

    @property
    def status_label(self) -> str:
        mapping = {
            "Active": "Aktif",
            "Banned": "Engelli",
            "Disabled": "Pasif",
            "Expired": "Suresi doldu",
        }
        return mapping.get(self.account_status, self.account_status or "Bilinmiyor")

    @property
    def connections_label(self) -> str:
        if self.active_connections is None and self.max_connections is None:
            return "Baglanti bilgisi yok"
        if self.active_connections is None:
            return f"Azami {self.max_connections}"
        if self.max_connections is None:
            return f"Aktif {self.active_connections}"
        return f"{self.active_connections} / {self.max_connections}"
