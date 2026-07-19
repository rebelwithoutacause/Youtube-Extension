"""Тънък клиент за YouTube Data API v3 с batch заявки и retry на HTTP 429."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50  # videos.list / channels.list поддържат до 50 ID на заявка


class YouTubeAPIError(Exception):
    """Хвърля се при невъзстановима грешка от YouTube Data API."""


class YouTubeQuotaExceededError(YouTubeAPIError):
    """Хвърля се, когато дневната квота на YouTube Data API е изчерпана."""


_QUOTA_ERROR_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}


class YouTubeClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._key_index = 0
        self._exhausted_key_indices: set[int] = set()

    @property
    def _current_key(self) -> str:
        return self._settings.api_keys[self._key_index]

    def _rotate_to_next_key(self) -> bool:
        """Маркира текущия ключ като изчерпан за днес и превключва на следващия
        наличен. Връща False, ако вече всички ключове са изчерпани."""
        self._exhausted_key_indices.add(self._key_index)
        for index in range(len(self._settings.api_keys)):
            if index not in self._exhausted_key_indices:
                if index != self._key_index:
                    logger.warning(
                        "Ключ %d/%d изчерпан — превключване на ключ %d/%d.",
                        self._key_index + 1, len(self._settings.api_keys),
                        index + 1, len(self._settings.api_keys),
                    )
                self._key_index = index
                return True
        return False

    def search_videos(
        self,
        query: str,
        published_after: str | None,
        published_before: str | None = None,
    ) -> list[str]:
        """
        Връща ID-та на видеа, отговарящи на заявката, като обхожда до
        `search_max_pages` страници (по search_max_results на страница) чрез
        pageToken пагинация — за по-голям пул кандидати преди филтриране
        (подобно на резултатите от нормално YouTube търсене), не само първите
        50. Всяка страница е отделна search.list заявка (100 units), затова
        броят страници е ограничен изрично заради дневната квота.
        """
        params: dict[str, Any] = {
            "part": "id",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": self._settings.search_max_results,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before

        video_ids: list[str] = []
        page_token: str | None = None

        for page in range(self._settings.search_max_pages):
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token

            data = self._get("search", page_params)
            video_ids.extend(item["id"]["videoId"] for item in data.get("items", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # YouTube понякога връща едно и също видео на повече от една страница
        # (напр. при разместване на relevance класирането между заявките за
        # различните страници) — премахваме дубликатите, запазвайки реда.
        unique_video_ids = list(dict.fromkeys(video_ids))

        logger.info(
            "search.list върна %d видео ID (%d уникални) за заявка '%s' (%d страница/и).",
            len(video_ids), len(unique_video_ids), query, page + 1,
        )
        return unique_video_ids

    def get_videos(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Връща snippet/statistics/contentDetails за подадените видеа, на batch-ове по 50."""
        items: list[dict[str, Any]] = []
        for chunk in _chunked(video_ids, _BATCH_SIZE):
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(chunk),
            }
            data = self._get("videos", params)
            items.extend(data.get("items", []))
        return items

    def get_channels(self, channel_ids: list[str]) -> list[dict[str, Any]]:
        """Връща statistics за подадените канали (уникализирани), на batch-ове по 50."""
        items: list[dict[str, Any]] = []
        unique_ids = list(dict.fromkeys(channel_ids))
        for chunk in _chunked(unique_ids, _BATCH_SIZE):
            params = {
                "part": "statistics",
                "id": ",".join(chunk),
            }
            data = self._get("channels", params)
            items.extend(data.get("items", []))
        return items

    def search_channels(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Търси канали по име (за разпознаване на "заявката е име на канал")."""
        params = {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": max_results,
        }
        data = self._get("search", params)
        return data.get("items", [])

    def get_channel_details(self, channel_id: str) -> dict[str, Any] | None:
        """Връща snippet/statistics за 1 канал по channel ID."""
        params = {
            "part": "snippet,statistics",
            "id": channel_id,
        }
        data = self._get("channels", params)
        items = data.get("items", [])
        return items[0] if items else None

    def get_channel_by_handle(self, handle: str) -> dict[str, Any] | None:
        """
        Връща snippet/statistics за 1 канал по @handle (напр. "@milkokukovbg").
        За разлика от search_channels (fuzzy, по заглавие), това е точен,
        еднозначен lookup — не зависи заглавието на канала да съвпада текстово
        със заявката (напр. канал "Милко Куков" на кирилица за @milkokukovbg).
        """
        handle_with_at = handle if handle.startswith("@") else f"@{handle}"
        params = {
            "part": "snippet,statistics",
            "forHandle": handle_with_at,
        }
        data = self._get("channels", params)
        items = data.get("items", [])
        return items[0] if items else None

    def search_channel_video_ids(
        self,
        channel_id: str,
        published_after: str | None,
        published_before: str | None,
        max_pages: int,
    ) -> list[str]:
        """
        Видеата на конкретен канал, сортирани от YouTube по viewCount в
        рамките на зададения период. Забележка: не ползваме
        channels.contentDetails.relatedPlaylists.uploads + playlistItems.list
        — тази "uploads playlist" връща playlistNotFound (HTTP 404) за част
        от каналите (позната особеност на YouTube API), докато search.list с
        channelId работи надеждно за всички канали и директно поддържа
        publishedAfter/Before + order=viewCount на ниво API.
        """
        params: dict[str, Any] = {
            "part": "id",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": 50,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before

        video_ids: list[str] = []
        page_token: str | None = None

        for _page in range(max_pages):
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token

            data = self._get("search", page_params)
            video_ids.extend(item["id"]["videoId"] for item in data.get("items", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return list(dict.fromkeys(video_ids))

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._settings.api_base_url}/{endpoint}"

        attempt = 0
        while True:
            attempt += 1
            request_params = {**params, "key": self._current_key}
            response = self._session.get(url, params=request_params, timeout=15)

            if response.status_code == 429 and attempt <= self._settings.max_retries:
                wait = self._settings.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "HTTP 429 от %s (опит %d/%d). Изчакване %.1fs преди повторен опит.",
                    endpoint, attempt, self._settings.max_retries, wait,
                )
                time.sleep(wait)
                continue

            if not response.ok:
                reason = _extract_error_reason(response)
                if reason in _QUOTA_ERROR_REASONS:
                    # Key rotation: превключваме на следващия наличен ключ и
                    # препробваме СЪЩАТА заявка — прозрачно за извикващия код,
                    # вместо да провалим цялото търсене заради 1 изчерпан ключ.
                    if self._rotate_to_next_key():
                        attempt = 0
                        continue
                    raise YouTubeQuotaExceededError(
                        f"Дневната квота е изчерпана за всичките {len(self._settings.api_keys)} "
                        f"конфигурирани ключа (reason={reason}). Изчакайте до утре или добавете "
                        "нов ключ."
                    )
                raise YouTubeAPIError(
                    f"{endpoint} върна HTTP {response.status_code}: {response.text}"
                )

            return response.json()


def _extract_error_reason(response: requests.Response) -> str | None:
    try:
        body = response.json()
        return body["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
