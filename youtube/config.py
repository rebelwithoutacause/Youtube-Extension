"""Конфигурация на приложението, зареждана от environment/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_keys: tuple[str, ...]
    api_base_url: str = "https://www.googleapis.com/youtube/v3"
    search_max_results: int = 50
    search_max_pages: int = 4  # 4 x 100 units = 400 units за search.list на търсене
    min_video_duration_seconds: int = 60
    subscriber_threshold: int = 100
    min_view_count_low_subs: int = 1000
    min_channel_subscriber_count: int = 100_000
    large_channel_subscriber_threshold: int = 500_000
    relevance_bypass_min_candidates: int = 5
    max_retries: int = 5
    retry_backoff_seconds: float = 1.0


def load_settings() -> Settings:
    """
    Поддържа множество ключове (key rotation): YOUTUBE_API_KEYS="key1,key2,key3"
    (разделени със запетая) — при изчерпване на текущия ключ, YouTubeClient
    автоматично превключва на следващия. За обратна съвместимост, ако
    YOUTUBE_API_KEYS липсва, се чете единичният YOUTUBE_API_KEY.
    """
    keys_env = os.getenv("YOUTUBE_API_KEYS")
    if keys_env:
        api_keys = tuple(key.strip() for key in keys_env.split(",") if key.strip())
    else:
        single_key = os.getenv("YOUTUBE_API_KEY")
        api_keys = (single_key,) if single_key else ()

    if not api_keys:
        raise RuntimeError(
            "YOUTUBE_API_KEYS (или YOUTUBE_API_KEY) не е зададен. "
            "Добавете го в .env файл (вижте .env.example)."
        )
    return Settings(api_keys=api_keys)
