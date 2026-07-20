"""Филтри за Shorts и за органичен интерес (viewCount vs subscriberCount)."""
from __future__ import annotations

import re

_DURATION_PATTERN = re.compile(
    r"P"
    r"(?:(?P<days>\d+)D)?"
    r"T?"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
)


def parse_iso8601_duration(duration: str) -> int:
    """Превръща ISO 8601 duration (напр. 'PT4M13S') в брой секунди."""
    match = _DURATION_PATTERN.fullmatch(duration)
    if not match:
        raise ValueError(f"Невалиден ISO 8601 duration формат: {duration}")

    parts = match.groupdict(default="0")
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def is_short(duration: str, min_seconds: int) -> bool:
    """Видео се третира като Shorts, ако продължителността му е под прага."""
    return parse_iso8601_duration(duration) < min_seconds


def _stem(word: str) -> str:
    """
    Груб, независим от езика "корен" на дума — отрязва кратък суфикс, за да
    поглъща граматически форми (мн. число, род, падеж) без пълен morphology
    анализатор. Работи еднакво за латиница и кирилица, тъй като разчита само
    на дължина в брой символи, не на конкретен език.
    """
    length = len(word)
    if length <= 4:
        return word
    if length <= 7:
        return word[:-1]
    return word[:-2]


def matches_query(title: str, description: str, query: str) -> bool:
    """
    Проверява дали ключовите (по-дълги) думи от заявката присъстват (по корен)
    във видимото заглавие/описание.

    ВАЖНО: не се използва като общ филтър за релевантност — заглавия често
    описват съдържанието с различни думи от търсената фраза (напр. канал
    "NOVA" (латиница) за търсене "Нова телевизия" (кирилица) никога няма да
    съвпадне буквално, макар да е точно търсеното). Затова се вика само като
    допълнителна проверка за видеа с подозрително висок ratio (виж
    search.py/_is_suspicious) — целта е единствено да хване очевиден
    tag-stuffing spam (напр. видео "PANKHA FAST" за търсене "fasting"), не да
    филтрира по обща релевантност.
    """
    haystack = f"{title} {description}".lower()
    words = [word for word in query.lower().split() if word]
    if not words:
        return True

    mandatory_words = [word for word in words if len(word) >= 5]
    required_words = mandatory_words or words

    return all(_stem(word) in haystack for word in required_words)


def passes_engagement_filter(
    subscriber_count: int,
    view_count: int,
    subscriber_threshold: int,
    min_view_count_low_subs: int,
) -> bool:
    """
    if subscriberCount >= threshold: viewCount > subscriberCount
    if subscriberCount <  threshold: viewCount >= min_view_count_low_subs
    """
    if subscriber_count >= subscriber_threshold:
        return view_count > subscriber_count
    return view_count >= min_view_count_low_subs
