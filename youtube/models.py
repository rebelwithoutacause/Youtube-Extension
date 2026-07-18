"""Типизирани модели на данните, връщани от YouTube Data API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VideoResult:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    subscriber_count: int
    view_count: int
    published_at: datetime

    @property
    def ratio(self) -> float:
        divisor = self.subscriber_count if self.subscriber_count > 0 else 1
        return self.view_count / divisor

    @property
    def video_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"
