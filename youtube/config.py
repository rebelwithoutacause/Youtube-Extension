"""Конфигурация на приложението, зареждана от environment/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_base_url: str = "https://www.googleapis.com/youtube/v3"
    search_max_results: int = 50
    search_max_pages: int = 4  # 4 x 100 units = 400 units за search.list на търсене
    min_video_duration_seconds: int = 60
    subscriber_threshold: int = 100
    min_view_count_low_subs: int = 1000
    min_channel_subscriber_count: int = 100_000
    large_channel_subscriber_threshold: int = 500_000
    max_retries: int = 5
    retry_backoff_seconds: float = 1.0


def load_settings() -> Settings:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY не е зададен. Добавете го в .env файл (вижте .env.example)."
        )
    return Settings(api_key=api_key)
