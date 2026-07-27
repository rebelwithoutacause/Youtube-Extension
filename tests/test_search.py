import pytest

from youtube.config import Settings
from youtube.search import (
    CHANNEL_SEARCH_MODE,
    VIDEO_SEARCH_MODE,
    find_matching_channel,
    resolve_channel,
    search_channel_videos,
    search_qualifying_videos,
)

from .helpers import FakeYouTubeClient, days_ago, make_channel, make_video


def make_settings(**overrides) -> Settings:
    return Settings(api_keys=("fake-key",), **overrides)


class TestChannelSizeNoLongerGates:
    """Regression coverage for dropping the >=100k subscriber hard filter."""

    def test_small_channel_with_breakout_video_qualifies(self):
        channel = make_channel("c1", title="Tiny Channel", subscriber_count=5_000)
        video = make_video(
            "v1", title="Fasting breakout", channel_id="c1",
            view_count=6_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[video], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert [r.video_id for r in results] == ["v1"]

    def test_tiny_channel_below_view_floor_is_excluded(self):
        # 50 subscribers is below the 100-subscriber engagement threshold, so the
        # small-channel view floor (2500) applies instead of views > subscribers.
        channel = make_channel("c1", title="Micro Channel", subscriber_count=50)
        video = make_video(
            "v1", title="Fasting clip", channel_id="c1",
            view_count=2_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[video], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert results == []

    def test_tiny_channel_at_2500_views_qualifies(self):
        channel = make_channel("c1", title="Micro Channel", subscriber_count=50)
        video = make_video(
            "v1", title="Fasting clip", channel_id="c1",
            view_count=2_500, published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[video], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert [r.video_id for r in results] == ["v1"]


class TestShortsFilter:
    def test_shorts_are_excluded_even_if_they_would_otherwise_qualify(self):
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        short_video = make_video(
            "v1", title="Fasting short", channel_id="c1",
            view_count=10_000, duration="PT30S", published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[short_video], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert results == []


class TestSortingIsPureRatio:
    """Regression coverage for dropping the 'large channels first' grouping."""

    def test_results_sorted_by_ratio_regardless_of_channel_size(self):
        big_channel = make_channel("big", title="Big Channel", subscriber_count=600_000)
        small_channel = make_channel("small", title="Small Channel", subscriber_count=1_000)

        # Big channel: modest breakout ratio (~1.01x).
        big_video = make_video(
            "big-v", title="Fasting big", channel_id="big",
            view_count=606_000, published_days_ago=1,
        )
        # Small channel: huge breakout ratio (10x) despite far fewer subscribers.
        small_video = make_video(
            "small-v", title="Fasting small", channel_id="small",
            view_count=10_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(
            videos=[big_video, small_video], channels=[big_channel, small_channel]
        )

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        # Highest ratio first, even though it belongs to the much smaller channel.
        assert [r.video_id for r in results] == ["small-v", "big-v"]


class TestRelevanceFilter:
    def test_irrelevant_video_dropped_from_small_pool(self):
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        matching = make_video(
            "v1", title="Fasting tips", channel_id="c1",
            view_count=5_000, published_days_ago=1,
        )
        unrelated = make_video(
            "v2", title="Completely unrelated video", channel_id="c1",
            view_count=5_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[matching, unrelated], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert [r.video_id for r in results] == ["v1"]

    def test_no_bypass_even_when_pool_is_large_and_all_irrelevant(self):
        # A previously-removed "bypass" used to assume a big-enough pool where
        # literally none match textually must be a brand/script mismatch, and
        # returned everything unfiltered. That produced false positives (e.g. a
        # completely unrelated recipe video for a fitness query) and was
        # dropped — such queries now go through explicit CHANNEL_SEARCH_MODE
        # instead. A large irrelevant pool must still be filtered to empty.
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        videos = [
            make_video(
                f"v{i}", title=f"Unrelated title {i}", channel_id="c1",
                view_count=5_000, published_days_ago=1,
            )
            for i in range(5)
        ]
        client = FakeYouTubeClient(videos=videos, channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert results == []

    def test_relevance_filters_small_irrelevant_pool_to_empty(self):
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        videos = [
            make_video(
                f"v{i}", title=f"Unrelated title {i}", channel_id="c1",
                view_count=5_000, published_days_ago=1,
            )
            for i in range(3)
        ]
        client = FakeYouTubeClient(videos=videos, channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="3m")

        assert results == []


class TestDateRangeCascade:
    def test_auto_cascade_falls_back_to_wider_tier(self):
        # 200 days ago clears the 3m (90d) and 6m (180d) tiers but not 1y (365d).
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        video = make_video(
            "v1", title="Fasting old", channel_id="c1",
            view_count=5_000, published_days_ago=200,
        )
        client = FakeYouTubeClient(videos=[video], channels=[channel])

        results = search_qualifying_videos("fasting", client, make_settings(), date_range="auto")

        assert [r.video_id for r in results] == ["v1"]

    def test_manual_date_range_does_not_cascade(self):
        channel = make_channel("c1", title="Channel", subscriber_count=1_000)
        video = make_video(
            "v1", title="Fasting old", channel_id="c1",
            view_count=5_000, published_days_ago=200,
        )
        client = FakeYouTubeClient(videos=[video], channels=[channel])

        # 200 days ago is outside the manually-selected 6m (180d) window, and
        # since date_range is explicit (not "auto"), there is no widening.
        results = search_qualifying_videos("fasting", client, make_settings(), date_range="6m")

        assert results == []


class TestChannelMode:
    def test_resolving_by_handle_switches_to_channel_mode(self):
        channel = make_channel("c1", title="Milko Kukov", subscriber_count=72_600)
        client = FakeYouTubeClient(channels_by_handle={"@milkokukovbg": channel})

        resolved = resolve_channel("@milkokukovbg", client)

        assert resolved is not None
        assert resolved["id"] == "c1"

    def test_channel_mode_applies_breakout_filter_and_sorts_by_ratio(self):
        # Channel mode applies the same breakout filter as topic search — a
        # channel's raw top-by-views videos are no longer shown unfiltered
        # (that previously let videos with views far below the channel's own
        # subscriber count show up labeled as "high organic interest").
        channel = make_channel("c1", title="Milko Kukov", subscriber_count=1_000)
        below_breakout_video = make_video(
            "v1", title="Older video", channel_id="c1",
            view_count=500, published_days_ago=1,
        )
        modest_breakout_video = make_video(
            "v2", title="Modest hit", channel_id="c1",
            view_count=2_000, published_days_ago=2,
        )
        big_breakout_video = make_video(
            "v3", title="Popular video", channel_id="c1",
            view_count=50_000, published_days_ago=3,
        )
        client = FakeYouTubeClient(
            videos=[below_breakout_video, modest_breakout_video, big_breakout_video],
            channel_video_ids={"c1": ["v1", "v2", "v3"]},
        )

        results = search_channel_videos(
            channel, client, make_settings(),
            published_after=days_ago(90), published_before=None,
        )

        # v1 excluded (views below subscribers); v3 has the higher ratio than v2.
        assert [r.video_id for r in results] == ["v3", "v2"]

    def test_channel_mode_still_excludes_shorts(self):
        channel = make_channel("c1", title="Milko Kukov", subscriber_count=1_000_000)
        short_video = make_video(
            "v1", title="A short", channel_id="c1",
            view_count=999_999, duration="PT20S", published_days_ago=1,
        )
        client = FakeYouTubeClient(videos=[short_video], channel_video_ids={"c1": ["v1"]})

        results = search_channel_videos(
            channel, client, make_settings(),
            published_after=days_ago(90), published_before=None,
        )

        assert results == []


class TestExplicitSearchMode:
    """search_qualifying_videos only resolves a channel when explicitly asked."""

    def test_video_mode_never_resolves_channel_even_on_exact_name_match(self):
        # A topic word ("movement") that happens to exactly match a real
        # channel's name must NOT be silently narrowed to that channel unless
        # CHANNEL_SEARCH_MODE was explicitly requested.
        channel = make_channel("c1", title="Movement", subscriber_count=1_000)
        matching_channel_video = make_video(
            "v1", title="Movement channel video", channel_id="c1",
            view_count=100, published_days_ago=1,
        )
        topic_channel = make_channel("c2", title="Other Channel", subscriber_count=100)
        topic_video = make_video(
            "v2", title="Movement in dance", channel_id="c2",
            view_count=5_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(
            videos=[matching_channel_video, topic_video],
            channels=[channel, topic_channel],
            channel_search_results={"movement": [{"snippet": {"channelId": "c1", "title": "Movement"}}]},
            channel_video_ids={"c1": ["v1"]},
        )

        results = search_qualifying_videos(
            "movement", client, make_settings(), date_range="3m", search_mode=VIDEO_SEARCH_MODE,
        )

        # Only the topic-search result qualifies (breakout: 5000 > 100); the
        # channel's own video ("v1", 100 views vs 1000 subs) is not even in
        # the candidate pool, since channel mode was never triggered.
        assert [r.video_id for r in results] == ["v2"]

    def test_channel_mode_raises_when_no_channel_matches_exactly(self):
        client = FakeYouTubeClient(channel_search_results={"no such channel": []})

        with pytest.raises(ValueError):
            search_qualifying_videos(
                "no such channel", client, make_settings(), date_range="3m",
                search_mode=CHANNEL_SEARCH_MODE,
            )

    def test_channel_mode_scopes_to_the_matched_channel(self):
        channel = make_channel("c1", title="Milko Kukov", subscriber_count=500)
        video = make_video(
            "v1", title="Some video", channel_id="c1",
            view_count=1_000, published_days_ago=1,
        )
        client = FakeYouTubeClient(
            videos=[video],
            channels=[channel],
            channels_by_handle={"@milkokukovbg": channel},
            channel_video_ids={"c1": ["v1"]},
        )

        results = search_qualifying_videos(
            "@milkokukovbg", client, make_settings(), date_range="3m",
            search_mode=CHANNEL_SEARCH_MODE,
        )

        assert [r.video_id for r in results] == ["v1"]


class TestFindMatchingChannel:
    def test_exact_title_match_after_cyrillic_transliteration(self):
        channel = make_channel("c1", title="Milko Atanasov", subscriber_count=72_600)
        client = FakeYouTubeClient(
            channels=[channel],
            channel_search_results={
                "милко атанасов": [{"snippet": {"channelId": "c1", "title": "Milko Atanasov"}}]
            },
        )

        found = find_matching_channel("милко атанасов", client)

        assert found is not None
        assert found["id"] == "c1"

    def test_substring_match_is_rejected(self):
        # Documented real regression: a topic search for "fasting" must not be
        # hijacked into channel mode just because "fasting" is a substring of an
        # unrelated big channel's normalized title ("Le Fasting" -> "lefasting").
        le_fasting = make_channel("c1", title="Le Fasting", subscriber_count=456_000)
        client = FakeYouTubeClient(
            channels=[le_fasting],
            channel_search_results={"fasting": [{"snippet": {"channelId": "c1", "title": "Le Fasting"}}]},
        )

        found = find_matching_channel("fasting", client)

        assert found is None

    def test_multiple_exact_matches_picks_the_one_with_most_subscribers(self):
        small = make_channel("small", title="The Clashers", subscriber_count=100)
        large = make_channel("large", title="The Clashers", subscriber_count=999_000)
        client = FakeYouTubeClient(
            channels=[small, large],
            channel_search_results={
                "the clashers": [
                    {"snippet": {"channelId": "small", "title": "The Clashers"}},
                    {"snippet": {"channelId": "large", "title": "The Clashers"}},
                ]
            },
        )

        found = find_matching_channel("the clashers", client)

        assert found is not None
        assert found["id"] == "large"

    def test_no_match_returns_none(self):
        client = FakeYouTubeClient(channel_search_results={"nonexistent": []})

        assert find_matching_channel("nonexistent", client) is None
