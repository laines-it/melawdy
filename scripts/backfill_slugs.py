"""
Заполняет content_items.slug для статей, у которых slug ещё пуст.

Запуск (из корня проекта, с активированным venv и настроенным DATABASE_URL):

    python -m scripts.backfill_slugs
    python -m scripts.backfill_slugs --dry-run   # только показать, что будет сделано

Скрипт идемпотентен: повторный запуск не трогает уже заполненные slug.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from typing import Iterable

from sqlalchemy import select


from backend.db import SessionLocal
from backend.models import ContentItem



_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in _TRANSLIT:
            result.append(_TRANSLIT[lower])
        else:
            result.append(ch)
    return "".join(result)


def slugify(title: str, fallback_id: int) -> str:
    """URL-safe slug. Если после чистки пусто — 'article-<id>'."""
    text = (title or "").strip()
    text = transliterate(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    cleaned = cleaned[:200].strip("-_")
    return cleaned or f"article-{fallback_id}"


def collect_existing_slugs(session, exclude_id: int | None = None) -> set[str]:
    stmt = select(ContentItem.slug).where(
        ContentItem.slug.is_not(None),
        ContentItem.slug != "",
    )
    if exclude_id is not None:
        stmt = stmt.where(ContentItem.id != exclude_id)
    return {row[0] for row in session.execute(stmt).all() if row[0]}


def unique_slug(base: str, taken: set[str], article_id: int) -> str:
    """Гарантирует уникальность: при коллизии добавляет -<id>, -<id>-2, ..."""
    candidate = base
    if candidate not in taken:
        return candidate
    candidate = f"{base}-{article_id}"
    if candidate not in taken:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in taken:
        suffix += 1
    return f"{candidate}-{suffix}"

from sqlalchemy import or_

def iter_missing(session) -> Iterable[ContentItem]:
    return session.scalars(
        select(ContentItem)
        .where(or_(ContentItem.slug.is_(None), ContentItem.slug == ""))
        .order_by(ContentItem.id)
    ).all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill content_items.slug")
    parser.add_argument("--dry-run", action="store_true", help="Только показать план, не писать в БД")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        missing = iter_missing(session)
        if not missing:
            print("Все статьи уже имеют slug. Нечего делать.")
            return 0

        taken = collect_existing_slugs(session)
        print(f"Найдено статей без slug: {len(missing)}")

        planned: list[tuple[int, str, str]] = []
        for item in missing:
            base = slugify(item.title, item.id)
            final = unique_slug(base, taken, item.id)
            taken.add(final)
            planned.append((item.id, item.title, final))

        for article_id, title, slug in planned:
            print(f"  #{article_id:>4}  {slug:<50}  ← {title[:60]}")

        if args.dry_run:
            print("\n--dry-run: изменения не записаны.")
            return 0

        for article_id, _title, slug in planned:
            item = session.get(ContentItem, article_id)
            if item is not None:
                item.slug = slug

        session.commit()
        print(f"\nГотово: обновлено {len(planned)} статей.")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
