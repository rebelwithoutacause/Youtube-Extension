"""CLI входна точка: търсене на YouTube видеа с висок органичен интерес."""
from __future__ import annotations

import argparse
import logging
import sys

from youtube.api import YouTubeAPIError, YouTubeClient, YouTubeQuotaExceededError
from youtube.config import load_settings
from youtube.models import VideoResult
from youtube.search import AUTO_DATE_RANGE, DATE_RANGE_PRESETS, search_qualifying_videos


def _configure_console_encoding() -> None:
    # Windows конзолите често ползват legacy кодови страници (cp1251 и др.),
    # които не могат да изведат emoji/по-редки Unicode символи в заглавия на видеа.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Търсене на нормални YouTube видеа (без Shorts) с висок органичен интерес.",
    )
    parser.add_argument("query", help="Ключова дума/фраза за търсене в YouTube.")
    parser.add_argument(
        "--range",
        dest="date_range",
        choices=[AUTO_DATE_RANGE, *sorted(DATE_RANGE_PRESETS)],
        default=AUTO_DATE_RANGE,
        help=(
            "Период на публикуване: 'auto' (по подразбиране) пробва 3m -> 6m -> 1y -> all "
            "автоматично, спирайки на първото ниво с резултати; или конкретна стойност "
            "(3m/6m/1y/1y+/all) за фиксиран период без каскада."
        ),
    )
    return parser.parse_args(argv)


def _print_table(results: list[VideoResult]) -> None:
    headers = [
        "Title",
        "Channel",
        "Subscribers",
        "Views",
        "Views/Subscribers",
        "Published",
        "Video URL",
    ]
    rows = [
        [
            result.title,
            result.channel_title,
            str(result.subscriber_count),
            str(result.view_count),
            f"{result.ratio:.2f}",
            result.published_at.strftime("%Y-%m-%d"),
            result.video_url,
        ]
        for result in results
    ]

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    def format_row(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    _configure_logging()
    args = _parse_args(argv)

    try:
        settings = load_settings()
    except RuntimeError as exc:
        logging.error(str(exc))
        return 1

    client = YouTubeClient(settings)

    try:
        results = search_qualifying_videos(args.query, client, settings, args.date_range)
    except YouTubeQuotaExceededError as exc:
        logging.error(str(exc))
        return 1
    except YouTubeAPIError as exc:
        logging.error("Грешка от YouTube API: %s", exc)
        return 1

    if not results:
        print("Няма видеа, отговарящи на зададените критерии.")
        return 0

    _print_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
