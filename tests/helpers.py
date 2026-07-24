"""Test-only factories and a fake YouTubeClient stand-in (no real HTTP calls)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def days_ago(days: float) -> str:
    return iso(datetime.now(timezone.utc) - timedelta(days=days))


def make_video(
    video_id: str,
    *,
    title: str,
    channel_id: str,
    channel_title: str = "Test Channel",
    view_count: int = 0,
    duration: str = "PT5M0S",
    published_days_ago: float = 1,
    description: str = "",
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "channelId": channel_id,
            "channelTitle": channel_title,
            "publishedAt": days_ago(published_days_ago),
        },
        "statistics": {"viewCount": str(view_count)},
        "contentDetails": {"duration": duration},
    }


def make_channel(channel_id: str, *, title: str, subscriber_count: int) -> dict:
    return {
        "id": channel_id,
        "snippet": {"title": title, "channelId": channel_id},
        "statistics": {"subscriberCount": str(subscriber_count)},
    }


def _within_range(published_at: str, published_after: str | None, published_before: str | None) -> bool:
    # publishedAt/published_after/published_before are all "%Y-%m-%dT%H:%M:%SZ" UTC strings
    # of identical width, so plain string comparison sorts the same as chronological order.
    if published_after is not None and published_at < published_after:
        return False
    if published_before is not None and published_at > published_before:
        return False
    return True


class FakeYouTubeClient:
    """
    Implements the subset of YouTubeClient's interface that youtube/search.py calls,
    backed by plain dicts instead of real HTTP requests to the YouTube Data API.
    """

    def __init__(
        self,
        videos: list[dict] | None = None,
        channels: list[dict] | None = None,
        channel_search_results: dict[str, list[dict]] | None = None,
        channels_by_handle: dict[str, dict] | None = None,
        channel_video_ids: dict[str, list[str]] | None = None,
    ) -> None:
        self.videos = videos or []
        self.channels = channels or []
        self.channel_search_results = channel_search_results or {}
        self.channels_by_handle = channels_by_handle or {}
        self.channel_video_ids = channel_video_ids or {}

    def search_videos(self, query, published_after, published_before=None):
        return [
            video["id"]
            for video in self.videos
            if _within_range(video["snippet"]["publishedAt"], published_after, published_before)
        ]

    def get_videos(self, video_ids):
        by_id = {video["id"]: video for video in self.videos}
        return [by_id[vid] for vid in video_ids if vid in by_id]

    def get_channels(self, channel_ids):
        by_id = {channel["id"]: channel for channel in self.channels}
        unique_ids = list(dict.fromkeys(channel_ids))
        return [by_id[cid] for cid in unique_ids if cid in by_id]

    def search_channels(self, query):
        return self.channel_search_results.get(query, [])

    def get_channel_details(self, channel_id):
        by_id = {channel["id"]: channel for channel in self.channels}
        return by_id.get(channel_id)

    def get_channel_by_handle(self, handle):
        # Mirrors YouTubeClient.get_channel_by_handle: the caller passes the
        # handle without "@" (regex capture group excludes it), normalize here.
        handle_with_at = handle if handle.startswith("@") else f"@{handle}"
        return self.channels_by_handle.get(handle_with_at)

    def search_channel_video_ids(self, channel_id, published_after, published_before, max_pages):
        by_id = {video["id"]: video for video in self.videos}
        return [
            vid
            for vid in self.channel_video_ids.get(channel_id, [])
            if vid in by_id
            and _within_range(by_id[vid]["snippet"]["publishedAt"], published_after, published_before)
        ]
