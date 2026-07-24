import pytest

from youtube.filters import (
    is_short,
    matches_query,
    parse_iso8601_duration,
    passes_engagement_filter,
)


class TestParseIso8601Duration:
    @pytest.mark.parametrize(
        "duration, expected_seconds",
        [
            ("PT4M13S", 4 * 60 + 13),
            ("PT1H2M3S", 3600 + 2 * 60 + 3),
            ("P1DT2H", 86400 + 2 * 3600),
            ("PT45S", 45),
            ("PT0S", 0),
        ],
    )
    def test_parses_known_formats(self, duration, expected_seconds):
        assert parse_iso8601_duration(duration) == expected_seconds

    def test_rejects_invalid_format(self):
        with pytest.raises(ValueError):
            parse_iso8601_duration("not-a-duration")


class TestIsShort:
    def test_below_threshold_is_short(self):
        assert is_short("PT45S", min_seconds=60) is True

    def test_at_threshold_is_not_short(self):
        assert is_short("PT60S", min_seconds=60) is False

    def test_above_threshold_is_not_short(self):
        assert is_short("PT5M", min_seconds=60) is False


class TestMatchesQuery:
    def test_empty_query_always_matches(self):
        assert matches_query("Anything at all", "", "") is True

    def test_title_containing_query_word_matches(self):
        assert matches_query("My Fasting Journey", "", "fasting") is True

    def test_description_is_also_searched(self):
        assert matches_query("Untitled video", "this one mentions fasting", "fasting") is True

    def test_real_world_spam_case_does_not_match(self):
        # Documented in search.py's rationale for calling matches_query only on
        # suspiciously-high-ratio candidates: a legitimate song title containing
        # "fast" as a substring must NOT count as a match for the topic "fasting".
        assert matches_query("TAEYANG - LIVE FAST DIE SLOW", "", "fasting") is False

    def test_short_words_are_all_mandatory_when_no_long_word_present(self):
        # Every word below 5 chars -> ALL of them become required.
        assert matches_query("cats and dogs playing", "", "cat dog") is True
        assert matches_query("only cats here", "", "cat dog") is False

    def test_long_word_makes_short_words_optional(self):
        # "fasting" (>=5 chars) is the only mandatory word; the short filler
        # word "a" is not required to be present.
        assert matches_query("Fasting for beginners", "", "a fasting") is True


class TestPassesEngagementFilter:
    def test_established_channel_breakout_qualifies(self):
        assert passes_engagement_filter(
            subscriber_count=100, view_count=101,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is True

    def test_established_channel_equal_views_does_not_qualify(self):
        # views must strictly exceed subscribers, not just match them.
        assert passes_engagement_filter(
            subscriber_count=100, view_count=100,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is False

    def test_established_channel_fewer_views_does_not_qualify(self):
        assert passes_engagement_filter(
            subscriber_count=10_000, view_count=9_999,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is False

    def test_large_channel_still_needs_strict_breakout(self):
        # No shortcut for big channels: 1M subs still needs > 1M views.
        assert passes_engagement_filter(
            subscriber_count=1_000_000, view_count=1_000_000,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is False

    def test_very_small_channel_meets_the_view_floor(self):
        assert passes_engagement_filter(
            subscriber_count=50, view_count=2500,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is True

    def test_very_small_channel_below_the_view_floor(self):
        assert passes_engagement_filter(
            subscriber_count=50, view_count=2499,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is False

    def test_brand_new_zero_subscriber_channel_uses_view_floor(self):
        assert passes_engagement_filter(
            subscriber_count=0, view_count=2500,
            subscriber_threshold=100, min_view_count_low_subs=2500,
        ) is True
