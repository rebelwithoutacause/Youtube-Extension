"""Конфигурация на приложението, зареждана от environment/.env."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_CONFIG_DIR_NAME = "YouTubeContentResearch"


def get_user_config_path() -> Path:
    """Per-user config location used by the installer wizard and first-run prompt."""
    appdata = os.getenv("APPDATA") or str(Path.home())
    return Path(appdata) / APP_CONFIG_DIR_NAME / ".env"


def _executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _load_env_cascade() -> None:
    """
    Зарежда .env от няколко възможни места, в ред на приоритет (първото
    намерено НЕ се презаписва от следващите — override=False):
    1. до изпълнимия файл (PyInstaller .exe до YouTubeContentResearch.exe,
       или repo root при 'python main.py')
    2. %APPDATA%\\YouTubeContentResearch\\.env (записан от installer wizard-а
       или от first-run prompt-а)
    3. текущата работна директория (стандартно поведение на load_dotenv() —
       запазено за development workflow-а)
    """
    for candidate in (_executable_dir() / ".env", get_user_config_path()):
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)
    load_dotenv(override=False)


_load_env_cascade()


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
