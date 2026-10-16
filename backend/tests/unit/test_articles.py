from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend import public


def test_article_uses_requested_id_and_returns_chunks_in_reading_order():
    session = Mock()
    session.scalar.return_value = SimpleNamespace(
        id=42, title="Авторство", summary="Описание",
        category=SimpleNamespace(id=3, name="Музыкальный бизнес"),
        chunks=[SimpleNamespace(chunk_index=9, body="Конец"),
                SimpleNamespace(chunk_index=0, body="Начало"),
                SimpleNamespace(chunk_index=2, body="Продолжение")],
    )
    result = public.read_article(42, session)
    assert result == {"id": "42", "title": "Авторство", "summary": "Описание",
                      "category": {"id": "3", "name": "Музыкальный бизнес"},
                      "chunks": ["Начало", "Продолжение", "Конец"]}
    statement = session.scalar.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "content_items.id = 42" in sql
    assert "content_items.status = 'published'" in sql
    assert "content_items.published_at <= now()" in sql


def test_article_without_category_or_chunks_remains_readable():
    session = Mock()
    session.scalar.return_value = SimpleNamespace(id=7, title="Статья", summary=None, category=None, chunks=[])
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
