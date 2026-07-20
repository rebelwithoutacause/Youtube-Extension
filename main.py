"""CLI входна точка: търсене на YouTube видеа с висок органичен интерес."""
from __future__ import annotations

import argparse
import logging
import sys

from youtube.api import YouTubeAPIError, YouTubeClient, YouTubeQuotaExceededError
from youtube.config import Settings, get_user_config_path, load_settings
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
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Ключова дума/фраза за търсене в YouTube. Ако липсва, стартира интерактивен режим.",
    )
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


def _prompt_for_api_keys() -> bool:
    """
    Пита интерактивно за поне един YouTube API ключ и го записва в
    %APPDATA%\\YouTubeContentResearch\\.env, за да работи приложението "из
    кутията" при публично разпространение (без вграден личен ключ). Връща
    True ако е записан ключ, False ако потребителят е прекъснал.
    """
    print()
    print("Не е намерен YouTube API ключ.")
    print("Вземете безплатен ключ от console.cloud.google.com (YouTube Data API v3)")
    print("и го въведете тук — ще бъде запазен само на този компютър.")
    try:
        raw = input("YouTube API ключ(ове), разделени със запетая: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if not raw:
        return False

    config_path = get_user_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f"YOUTUBE_API_KEYS={raw}\n", encoding="utf-8")
    print(f"Записано в {config_path}\n")
    return True


def _load_settings_interactive() -> Settings | None:
    try:
        return load_settings()
    except RuntimeError as exc:
        if not sys.stdin.isatty():
            logging.error(str(exc))
            return None
        if not _prompt_for_api_keys():
            logging.error(str(exc))
            return None
        try:
            return load_settings()
        except RuntimeError as retry_exc:
            logging.error(str(retry_exc))
            return None


def _run_search(query: str, date_range: str, client: YouTubeClient, settings: Settings) -> int:
    try:
        results = search_qualifying_videos(query, client, settings, date_range)
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


def _run_interactive(client: YouTubeClient, settings: Settings) -> int:
    """Меню за double-click стартиране (без CLI аргументи): пита за заявка/период в цикъл."""
    range_choices = [AUTO_DATE_RANGE, *sorted(DATE_RANGE_PRESETS)]
    print("=== YouTube Content Research Tool ===")
    print("Намира видеа с органичен интерес над нормата за канала им.\n")

    exit_code = 0
    try:
        while True:
            try:
                query = input("Ключова дума или канал (Enter за изход): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query:
                break

            range_prompt = f"Период [{'/'.join(range_choices)}] (Enter = {AUTO_DATE_RANGE}): "
            try:
                date_range = input(range_prompt).strip() or AUTO_DATE_RANGE
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if date_range not in range_choices:
                print(f"Непознат период '{date_range}', ползвам '{AUTO_DATE_RANGE}'.")
                date_range = AUTO_DATE_RANGE

            print()
            exit_code = _run_search(query, date_range, client, settings)
            print()
    finally:
        try:
            input("Натиснете Enter за изход...")
        except (EOFError, KeyboardInterrupt):
            print()

    return exit_code


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    _configure_logging()
    args = _parse_args(argv)

    settings = _load_settings_interactive()
    if settings is None:
        return 1

    client = YouTubeClient(settings)

    if args.query is None:
        return _run_interactive(client, settings)

    return _run_search(args.query, args.date_range, client, settings)


if __name__ == "__main__":
    sys.exit(main())
