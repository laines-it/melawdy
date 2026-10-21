from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend import public


@pytest.mark.parametrize("key", ["42", "coauthors-agreement", "авторство-песни"])
def test_article_uses_requested_id_or_slug_and_returns_chunks_in_reading_order(key):
    session = Mock()
    session.scalar.return_value = SimpleNamespace(
        id=42, slug="авторство-песни", title="Авторство", summary="Описание", published_at=None,
        category=SimpleNamespace(id=3, name="Музыкальный бизнес"),
        chunks=[SimpleNamespace(chunk_index=9, body="Конец"),
                SimpleNamespace(chunk_index=0, body="Начало"),
                SimpleNamespace(chunk_index=2, body="Продолжение")],
    )
    result = public.read_article(key, session)
    assert result == {"id": "42", "slug": "авторство-песни", "link_title": None, "published_at": None, "title": "Авторство", "summary": "Описание",
                      "category": {"id": "3", "name": "Музыкальный бизнес"},
                      "chunks": ["Начало", "Продолжение", "Конец"]}
    statement = session.scalar.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert ("content_items.id = 42" if key == "42" else "content_items.slug =") in sql
    if key != "42":
        assert key in statement.compile().params.values()
    assert "content_items.status = 'published'" in sql
    assert "content_items.published_at <= now()" in sql


def test_article_without_category_or_chunks_remains_readable():
    session = Mock()
    session.scalar.return_value = SimpleNamespace(id=7, slug="article", title="Статья", summary=None, category=None, chunks=[], published_at=None)
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
