from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend import public


def test_article_returns_chunks_in_reading_order():
    session = Mock()
    session.scalar.return_value = SimpleNamespace(
        id=42, title="Авторство", summary="Описание",
        published_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        category=SimpleNamespace(id=3, name="Музыкальный бизнес"),
        chunks=[SimpleNamespace(chunk_index=9, body="Конец"),
                SimpleNamespace(chunk_index=0, body="Начало"),
                SimpleNamespace(chunk_index=2, body="Продолжение")],
    )
    result = public.read_article(42, session)
    assert result["chunks"] == ["Начало", "Продолжение", "Конец"]
    assert result["updated_at"] == session.scalar.return_value.updated_at
    assert result["published_at"] == session.scalar.return_value.published_at


def test_article_without_category_or_chunks_remains_readable():
    session = Mock()
    session.scalar.return_value = SimpleNamespace(id=7, title="Статья", summary=None, category=None, chunks=[],
                                                   published_at=None, updated_at=None)
    result = public.read_article(7, session)
    assert result["category"] is None
    assert result["chunks"] == []


def test_missing_or_unpublished_article_returns_404():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        public.read_article(404, session)
    assert error.value.status_code == 404
    assert error.value.detail == "Статья не найдена"
