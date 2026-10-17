import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend import public
from backend.content_repository import ContentSearchRepository
from backend.db import get_session
from backend.main import app
from ml import embedding_search, index_content
from ml.constants import EMBEDDING_DIMENSIONS
from ml.embeddings import EmbeddingConfigurationError, LegalEmbedder, get_embedder
from ml.tfidf import SearchChunk, SearchHit


def vector():
    return [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


def model_stub():
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = 384
    model.tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    model.encode.return_value = [vector()]
    return model


@pytest.fixture(autouse=True)
def clear_model_cache():
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


def test_default_model_loads_through_sentence_transformer_once(monkeypatch):
    factory = Mock(return_value=model_stub())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    first = get_embedder()
    assert get_embedder() is first
    factory.assert_called_once_with(
        "alekseevpavel04/multilingual-e5-small-ru-law", device="cpu",
        local_files_only=False, trust_remote_code=False,
    )


def test_local_model_override_is_loaded_offline(monkeypatch, tmp_path):
    factory = Mock(return_value=model_stub())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    get_embedder(str(tmp_path))
    factory.assert_called_once_with(str(tmp_path), device="cpu", local_files_only=True, trust_remote_code=False)


def test_missing_dependency_has_an_actionable_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbeddingConfigurationError, match="ml/requirements.txt"):
        get_embedder()


@pytest.mark.parametrize("exception", [OSError("download failed"), RuntimeError("offline")])
def test_model_load_errors_are_reported_as_configuration_errors(monkeypatch, exception):
    factory = Mock(side_effect=exception)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    with pytest.raises(EmbeddingConfigurationError):
        get_embedder()


def test_old_model_dimension_is_rejected(monkeypatch):
    model = model_stub()
    model.get_sentence_embedding_dimension.return_value = 1024
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Mock(return_value=model)))
    with pytest.raises(EmbeddingConfigurationError):
        get_embedder()


def test_e5_prefixes_and_normalization_follow_model_contract():
    model = model_stub()
    embedder = LegalEmbedder(model)
    assert len(embedder.encode_query(" защитить трек ")) == 384
    assert model.encode.call_args.args[0] == ["query: защитить трек"]
    embedder.encode_documents([" Документ "])
    assert model.encode.call_args.args[0] == ["passage: Документ"]
    assert model.encode.call_args.kwargs["normalize_embeddings"] is True
    assert model.tokenizer.call_args.args[0] == ["passage: Документ"]
    assert model.max_seq_length == 512


def test_empty_documents_do_not_trigger_inference():
    model = model_stub()
    embedder = LegalEmbedder(model)
    assert embedder.encode_documents([]) == []
    with pytest.raises(ValueError):
        embedder.encode_documents([" "])
    model.encode.assert_not_called()


def test_search_encodes_only_query_and_uses_article_ranking(monkeypatch):
    embedder = Mock()
    embedder.encode_query.return_value = vector()
    repository = Mock(spec=ContentSearchRepository)
    repository.nearest_articles.return_value = [SearchHit(SearchChunk(1, 10, "Текст"), 0.9)]
    session = Mock(spec=Session)
    factory = Mock(return_value=embedder)
    monkeypatch.setattr(embedding_search, "get_embedder", factory)
    monkeypatch.setattr("backend.content_repository.ContentSearchRepository", lambda actual: repository)
    result = embedding_search.search_embeddings("защитить трек", session=session, limit=3)
    assert [hit.chunk.content_item_id for hit in result] == [10]
    embedder.encode_query.assert_called_once_with("защитить трек")
    embedder.encode_documents.assert_not_called()
    repository.nearest_articles.assert_called_once_with(vector(), 3)
    session.commit.assert_not_called()


@pytest.mark.parametrize("query,limit", [(" ", 10), ("Запрос", 0), ("Запрос", 101)])
def test_invalid_search_does_not_access_database_or_model(monkeypatch, query, limit):
    factory = Mock()
    monkeypatch.setattr(embedding_search, "get_embedder", factory)
    with pytest.raises(ValueError):
        embedding_search.search_embeddings(query, limit=limit)
    factory.assert_not_called()


def test_article_ranking_filters_publication_and_deduplicates_before_limit():
    session = Mock(spec=Session)
    session.execute.return_value = [SimpleNamespace(id=8, content_item_id=2, body="Текст", distance=0.2)]
    hits = ContentSearchRepository(session).nearest_articles(vector(), limit=3)
    assert hits[0].score == pytest.approx(0.8)
    assert hits[0].chunk.content_item_id == 2
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "row_number() OVER (PARTITION BY content_item_chunks.content_item_id ORDER BY" in sql
    assert "content_item_chunks.embedding <=>" in sql
    assert "content_item_chunks.embedding IS NOT NULL" in sql
    assert "content_items.status" in sql and "content_items.published_at <= now()" in sql
    assert "WHERE anon_1.chunk_rank =" in sql
    assert "ORDER BY anon_1.distance, anon_1.content_item_id" in sql
    assert statement.compile().params["param_1"] == 3


@pytest.mark.parametrize("values,limit", [([], 3), (vector(), 0), (vector(), 101)])
def test_invalid_ranking_does_not_execute_sql(values, limit):
    session = Mock(spec=Session)
    with pytest.raises(ValueError):
        ContentSearchRepository(session).nearest_articles(values, limit)
    session.execute.assert_not_called()


@pytest.mark.parametrize("hits,metadata,expected", [
    ([SearchHit(SearchChunk(8, 2, "Найденный абзац"), 0.8)],
     [SimpleNamespace(id=2, title="Заголовок", summary="Описание")],
     {"article_ids": ["2"], "title": "Заголовок", "summary": "Описание"}),
    ([], [], {"article_ids": [], "title": None, "summary": None}),
    ([SearchHit(SearchChunk(8, 2, "Скрытый материал"), 0.8)], [],
     {"article_ids": [], "title": None, "summary": None}),
    ([SearchHit(SearchChunk(8, 2, "Первый"), 0.8), SearchHit(SearchChunk(9, 2, "Второй"), 0.7),
      SearchHit(SearchChunk(10, 3, "Третий"), 0.6)],
     [SimpleNamespace(id=3, title="Другой", summary=None), SimpleNamespace(id=2, title="Заголовок", summary="Описание")],
     {"article_ids": ["2", "3"], "title": "Заголовок", "summary": "Описание"}),
])
def test_public_search_defaults_to_embeddings_and_preserves_response_contract(monkeypatch, hits, metadata, expected):
    search = Mock(return_value=hits)
    monkeypatch.setattr(public, "search_embeddings", search)
    session = Mock(spec=Session)
    session.execute.return_value.all.return_value = metadata
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/search", params={"query": "защитить трек", "limit": 3})
            assert client.get("/api/v1/public/search", params={"query": "трек", "method": "unknown"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert response.status_code == 200
    assert response.json() == expected
    search.assert_called_once_with("защитить трек", session=session, limit=3)


@pytest.mark.parametrize("error,status", [
    (EmbeddingConfigurationError("Не удалось загрузить модель"), 503),
    (ValueError("Split text into chunks of at most 512 tokens"), 422),
])
def test_public_search_reports_model_and_input_errors(monkeypatch, error, status):
    monkeypatch.setattr(public, "search_embeddings", Mock(side_effect=error))
    with pytest.raises(public.HTTPException) as result:
        public.search(Mock(), query="Запрос")
    assert result.value.status_code == status
    assert result.value.detail == str(error)


def test_empty_search_does_not_fetch_titles(monkeypatch):
    monkeypatch.setattr(public, "search_embeddings", Mock(return_value=[]))
    session = Mock(spec=Session)
    assert public.search(session, query="Запрос") == {"article_ids": [], "title": None, "summary": None}
    session.execute.assert_not_called()


def test_indexing_preserves_batch_and_concurrent_edit_checks(monkeypatch, capsys):
    row = SimpleNamespace(id=7, body="Текст для индексации", updated_at="revision")
    session = Mock(spec=Session)
    session.execute.side_effect = [Mock(all=lambda: [row]), Mock(rowcount=1), Mock(all=lambda: [])]
    context = Mock()
    context.__enter__ = Mock(return_value=session)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(index_content, "SessionLocal", lambda: context)
    embedder = Mock()
    embedder.encode_documents.return_value = [vector()]
    monkeypatch.setattr(index_content, "get_embedder", lambda *args: embedder)
    monkeypatch.setattr(sys, "argv", ["index_content", "--batch-size", "2"])
    index_content.main()
    embedder.encode_documents.assert_called_once_with([row.body])
    session.commit.assert_called_once()
    update = session.execute.call_args_list[1].args[0]
    assert "content_item_chunks.updated_at =" in str(update)
    assert update.compile().params["embedding"] == vector()
    assert "Indexed 1 chunks" in capsys.readouterr().out
