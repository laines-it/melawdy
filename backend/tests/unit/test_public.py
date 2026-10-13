from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from backend import public


def test_title_search_returns_string_ids_and_only_searches_public_content():
    session = Mock()
    session.scalars.return_value = [7, 9007199254740993]

    assert public.search_articles(session, "  Авторское право  ") == ["7", "9007199254740993"]

    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert sql.startswith("SELECT content_items.id ")
    assert "content_items.title ILIKE" in sql
    assert "Авторское право" in compiled.params.values()
    assert "published" in compiled.params.values()
    assert "content_items.published_at <= now()" in sql
    assert "ORDER BY content_items.id" in sql


@pytest.mark.parametrize("query,escaped", [
    ("100%", "100/%"), ("a_b", "a/_b"), ("a/b", "a//b"),
    ("' OR 1=1 --", "' OR 1=1 --"),
])
def test_title_search_treats_wildcards_and_sql_as_literal_text(query, escaped):
    session = Mock()
    session.scalars.return_value = []

    assert public.search_articles(session, query) == []

    compiled = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert escaped in compiled.params.values()
    assert "ESCAPE '/'" in str(compiled)
    assert query not in str(compiled)


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_title_search_rejects_blank_queries_without_database_access(query):
    session = Mock()

    with pytest.raises(HTTPException) as error:
        public.search_articles(session, query)

    assert error.value.status_code == 422
    session.scalars.assert_not_called()
