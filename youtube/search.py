"""Оркестрация: търсене -> обогатяване с данни -> филтриране -> сортиране."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from .api import YouTubeClient
from .config import Settings
from .filters import is_short, matches_query, passes_engagement_filter
from .models import VideoResult

logger = logging.getLogger(__name__)

_CHANNEL_MAX_PAGES = 5  # 5 x 50 = до 250 скорошни видеа от канала (евтино: 1 unit/страница)

# (published_after_days, published_before_days) спрямо "сега".
# "1y+" няма долна граница (published_after) — обхваща всичко по-старо от 1г.
# "all" няма никакво ограничение по дата — финалното ниво на auto-каскадата.
DATE_RANGE_PRESETS: dict[str, tuple[int | None, int | None]] = {
    "3m": (90, None),
    "6m": (180, None),
    "1y": (365, None),
    "1y+": (None, 365),
    "all": (None, None),
}
DEFAULT_DATE_RANGE = "3m"

# Автоматична каскада (изискване на клиента): пробвай последните 3 месеца
# първо; ако няма резултати, разшири до 6 месеца, после 1 година, после без
# ограничение — спира на първото ниво с поне 1 резултат.
AUTO_DATE_RANGE = "auto"
_AUTO_CASCADE_TIERS = ["3m", "6m", "1y", "all"]

# Разпознава @handle (самостоятелно или в URL, напр.
# "https://www.youtube.com/@milkokukovbg") и directory-style channel URL-и.
_HANDLE_PATTERN = re.compile(r"(?:youtube\.com/)?@([\w.-]+)", re.IGNORECASE)
_CHANNEL_ID_PATTERN = re.compile(r"youtube\.com/channel/(UC[\w-]{20,})", re.IGNORECASE)


def resolve_channel(query: str, client: YouTubeClient) -> dict | None:
    """
    Опитва да открие канал от заявката по (в ред на приоритет):
    1. @handle (директен, еднозначен lookup — работи дори когато реалното
       заглавие на канала е на друга писменост от заявката, напр. канал
       "Милко Куков" на кирилица за заявка "@milkokukovbg").
    2. Директен channel ID (youtube.com/channel/UC...).
    3. Точно съвпадение по заглавие (виж find_matching_channel).
    """
    handle_match = _HANDLE_PATTERN.search(query)
    if handle_match:
        channel = client.get_channel_by_handle(handle_match.group(1))
        if channel:
            return channel

    channel_id_match = _CHANNEL_ID_PATTERN.search(query)
    if channel_id_match:
        channel = client.get_channel_details(channel_id_match.group(1))
        if channel:
            return channel

    return find_matching_channel(query, client)


def search_qualifying_videos(
    query: str,
    client: YouTubeClient,
    settings: Settings,
    date_range: str = DEFAULT_DATE_RANGE,
) -> list[VideoResult]:
    """
    date_range="auto" пуска клиентската каскада: 3 месеца -> 6 месеца ->
    1 година -> без ограничение, спирайки на първото ниво с поне 1 резултат
    (изискване: "Priority: Last 3 months, then 6 months, then 1 year, then
    all" — да се засичат текущи тенденции, но без да се връща изкуствено 0
    резултата само защото зададеният период е твърде тесен). Конкретна
    стойност (3m/6m/1y/1y+/all) прави еднократно търсене само с този период,
    без каскада — за ръчно избран от потребителя период.
    """
    channel = resolve_channel(query, client)

    if date_range == AUTO_DATE_RANGE:
        tiers = _AUTO_CASCADE_TIERS
    else:
        if date_range not in DATE_RANGE_PRESETS:
            raise ValueError(
                f"Непознат период '{date_range}'. Валидни стойности: "
                f"{sorted(DATE_RANGE_PRESETS)} или '{AUTO_DATE_RANGE}'."
            )
        tiers = [date_range]

    for tier in tiers:
        after_days, before_days = DATE_RANGE_PRESETS[tier]
        published_after = _days_ago_cutoff(after_days) if after_days else None
        published_before = _days_ago_cutoff(before_days) if before_days else None

        if channel is not None:
            results = search_channel_videos(
                channel, client, settings, published_after, published_before
            )
        else:
            results = _search_topic_videos(
                query, client, settings, published_after, published_before
            )

        if results:
            if tier != tiers[0]:
                logger.info(
                    "Автоматична каскада: спряно на ниво '%s' (по-тесните периоди бяха празни).",
                    tier,
                )
            return results

    return []


def _search_topic_videos(
    query: str,
    client: YouTubeClient,
    settings: Settings,
    published_after: str | None,
    published_before: str | None,
) -> list[VideoResult]:
    video_ids = client.search_videos(query, published_after, published_before)
    if not video_ids:
        return []

    videos = client.get_videos(video_ids)

    # Някои резултати (напр. livestream-и/premiere-и в нестандартно състояние,
    # или видеа, изтрити/направени private между индексирането от search.list
    # и извикването на videos.list) се връщат без пълен contentDetails/snippet
    # — пропускаме ги вместо да гръмнем с KeyError.
    complete_videos = [video for video in videos if _has_required_fields(video)]
    if len(complete_videos) != len(videos):
        logger.warning(
            "%d видеа пропуснати поради непълни данни (contentDetails/snippet).",
            len(videos) - len(complete_videos),
        )

    long_videos = [
        video
        for video in complete_videos
        if not is_short(
            video["contentDetails"]["duration"],
            settings.min_video_duration_seconds,
        )
    ]
    logger.info(
        "%d от %d видеа отпаднаха като Shorts (< %ds).",
        len(complete_videos) - len(long_videos),
        len(complete_videos),
        settings.min_video_duration_seconds,
    )

    channel_ids = [video["snippet"]["channelId"] for video in long_videos]
    channels = client.get_channels(channel_ids)
    subscriber_by_channel = {
        channel["id"]: int(channel["statistics"].get("subscriberCount", 0))
        for channel in channels
    }

    # Твърд филтър: само канали с >= min_channel_subscriber_count абонати
    # (изискване на клиента — търсим пробивни видеа на established канали,
    # не "hidden gems" от произволен размер канал).
    big_channel_videos = [
        video
        for video in long_videos
        if subscriber_by_channel.get(video["snippet"]["channelId"], 0)
        >= settings.min_channel_subscriber_count
    ]
    logger.info(
        "%d от %d видеа отпаднаха заради канал с < %s абонати.",
        len(long_videos) - len(big_channel_videos),
        len(long_videos),
        f"{settings.min_channel_subscriber_count:,}",
    )

    engagement_qualified: list[tuple[dict, VideoResult]] = []
    for video in big_channel_videos:
        channel_id = video["snippet"]["channelId"]
        subscriber_count = subscriber_by_channel.get(channel_id, 0)
        view_count = int(video["statistics"].get("viewCount", 0))

        if not passes_engagement_filter(
            subscriber_count,
            view_count,
            settings.subscriber_threshold,
            settings.min_view_count_low_subs,
        ):
            continue

        candidate = VideoResult(
            video_id=video["id"],
            title=video["snippet"]["title"],
            channel_id=channel_id,
            channel_title=video["snippet"]["channelTitle"],
            subscriber_count=subscriber_count,
            view_count=view_count,
            published_at=_parse_datetime(video["snippet"]["publishedAt"]),
        )
        engagement_qualified.append((video, candidate))

    relevant_results = [
        candidate
        for video, candidate in engagement_qualified
        if matches_query(video["snippet"]["title"], video["snippet"].get("description", ""), query)
    ]

    if relevant_results:
        # Нормален случай: релевантността отсява spam/tag-stuffing (напр.
        # "TAEYANG - LIVE FAST DIE SLOW" за търсене "fasting") без да изчиства
        # всичко.
        results = relevant_results
        logger.info(
            "%d видеа отпаднаха като нерелевантни, %d останаха.",
            len(engagement_qualified) - len(relevant_results),
            len(relevant_results),
        )
    elif len(engagement_qualified) >= settings.relevance_bypass_min_candidates:
        # Релевантността би изчистила абсолютно всички кандидати, но пулът е
        # достатъчно голям (>= relevance_bypass_min_candidates), за да е
        # правдоподобно, че причината е бранд/скрипт разлика (напр. "Нова
        # телевизия" срещу канал "NOVA" на латиница, ~40-200 кандидата, всички
        # провалени) — не че всеки от толкова много резултати е случайно
        # ирелевантен. В този случай филтърът се прескача за тази заявка.
        results = [candidate for _video, candidate in engagement_qualified]
        logger.info(
            "Филтърът за релевантност би изчистил всички %d резултата (пул >= %d) — "
            "прескочен за тази заявка (вероятно бранд/скрипт разлика).",
            len(results),
            settings.relevance_bypass_min_candidates,
        )
    else:
        # Малък пул (< relevance_bypass_min_candidates) и никой не минава
        # релевантността — много по-вероятно е кандидатите просто да са
        # ирелевантни (напр. едно случайно видео на хинди за заявка "мини
        # книжка за личните финанси"), не системна бранд/скрипт разлика.
        # Доверяваме се на филтъра и връщаме празно, вместо grasping at straws.
        results = []
        if engagement_qualified:
            logger.info(
                "%d кандидат(и) провалиха релевантността, пулът е твърде малък "
                "(< %d) за bypass — връщаме 0 резултата.",
                len(engagement_qualified),
                settings.relevance_bypass_min_candidates,
            )

    sorted_results = _group_sort(results, settings.large_channel_subscriber_threshold)
    logger.info("%d видеа отговарят на всички критерии.", len(sorted_results))
    return sorted_results


def _group_sort(
    results: list[VideoResult], large_channel_subscriber_threshold: int
) -> list[VideoResult]:
    """
    Две групи: (1) видеа от големи канали (>= threshold абонати), сортирани по
    subscriberCount низходящо; (2) останалите, сортирани по ratio низходящо
    (както досега). Групи 1 излиза първа.
    """
    top_channel_videos = [
        r for r in results if r.subscriber_count >= large_channel_subscriber_threshold
    ]
    other_videos = [
        r for r in results if r.subscriber_count < large_channel_subscriber_threshold
    ]
    top_channel_videos.sort(key=lambda r: r.subscriber_count, reverse=True)
    other_videos.sort(key=lambda r: r.ratio, reverse=True)
    return top_channel_videos + other_videos


# Стандартна българска транслитерация кирилица -> латиница. Позволява
# заявка на кирилица ("милко атанасов") да съвпадне с канал, чието реално
# заглавие е изписано на латиница ("Milko Atanasov") — без нея, единственото
# "точно" съвпадение би бил различен, несвързан канал със същото име на
# кирилица (напр. открихме реален случай: обскурен канал с 4 абоната вместо
# истинския с 72 600, само защото писмеността на заявката и заглавието не
# съвпадат буквено, макар да звучат идентично).
_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a",
    "ь": "y", "ю": "yu", "я": "ya",
}


def _normalize_channel_text(text: str) -> str:
    transliterated = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in text.lower())
    return re.sub(r"[^a-z0-9]", "", transliterated)


def find_matching_channel(query: str, client: YouTubeClient) -> dict | None:
    """
    Търси дали заявката е име на съществуващ канал (напр. "Milko Kukov",
    "The Clashers"), не тематична ключова дума. Съвпадение се приема САМО при
    точно (нормализирано: без интервали/пунктуация, lower-case) съвпадение на
    цялото заглавие на канала — НЕ при частично/substring съвпадение.

    Substring съвпадение (напр. "query в title" или обратното) изглеждаше
    удобно за скъсени имена, но на практика хващаше грешни случаи: заявка
    "fasting" (обща тема) съвпадаше с реален, голям канал "Le Fasting"
    (456k абонати), защото "fasting" е substring на "lefasting" — превръщайки
    нормално тематично търсене в погрешен channel режим. Точното съвпадение
    покрива демонстрираните случаи ("The Clashers", "Milko Kukov" - и двете
    точни съвпадения) без този риск.

    Ако няколко канала съвпадат точно (рядко, но възможно), избира този с
    най-много абонати — по-вероятно е "истинският"/търсеният канал, не празен/
    изоставен дубликат.
    """
    normalized_query = _normalize_channel_text(query)
    if not normalized_query:
        return None

    candidates = client.search_channels(query)
    matching_ids = [
        candidate["snippet"]["channelId"]
        for candidate in candidates
        if _normalize_channel_text(candidate["snippet"]["title"]) == normalized_query
    ]
    if not matching_ids:
        return None

    channels = [client.get_channel_details(channel_id) for channel_id in matching_ids]
    channels = [channel for channel in channels if channel is not None]
    if not channels:
        return None

    return max(channels, key=lambda channel: int(channel["statistics"].get("subscriberCount", 0)))


def search_channel_videos(
    channel: dict,
    client: YouTubeClient,
    settings: Settings,
    published_after: str | None,
    published_before: str | None,
) -> list[VideoResult]:
    """
    Канал-режим: заявката съвпада с име на канал — показваме НЕГОВИТЕ видеа
    от избрания период, сортирани по гледания (без Shorts), БЕЗ engagement
    филтъра (viewCount > subscriberCount), защото целта тук не е да се открият
    "подценени" видеа, а просто топ съдържанието на конкретния канал.
    """
    channel_id = channel["id"]
    channel_title = channel["snippet"]["title"]
    subscriber_count = int(channel["statistics"].get("subscriberCount", 0))

    video_ids = client.search_channel_video_ids(
        channel_id, published_after, published_before, _CHANNEL_MAX_PAGES
    )
    if not video_ids:
        return []

    videos = client.get_videos(video_ids)
    complete_videos = [video for video in videos if _has_required_fields(video)]

    long_videos = [
        video
        for video in complete_videos
        if not is_short(video["contentDetails"]["duration"], settings.min_video_duration_seconds)
    ]

    results = [
        VideoResult(
            video_id=video["id"],
            title=video["snippet"]["title"],
            channel_id=channel_id,
            channel_title=channel_title,
            subscriber_count=subscriber_count,
            view_count=int(video["statistics"].get("viewCount", 0)),
            published_at=_parse_datetime(video["snippet"]["publishedAt"]),
        )
        for video in long_videos
    ]
    results.sort(key=lambda r: r.view_count, reverse=True)
    logger.info(
        "Channel режим за '%s': %d видеа в периода, %d след Shorts филтър.",
        channel_title, len(complete_videos), len(results),
    )
    return results


def _has_required_fields(video: dict) -> bool:
    snippet = video.get("snippet") or {}
    content_details = video.get("contentDetails") or {}
    return bool(content_details.get("duration")) and bool(snippet.get("title")) and bool(
        snippet.get("channelId")
    )


def _days_ago_cutoff(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
