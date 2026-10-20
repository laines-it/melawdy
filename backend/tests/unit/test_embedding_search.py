import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend import public
from backend.content_repository import ContentSearchRepository
from backend.db import get_session
from backend.main import app
from ml import embedding_search
from ml.constants import EMBEDDING_DIMENSIONS
from ml.embeddings import EmbeddingConfigurationError, LegalEmbedder, get_embedder
from ml.hybrid_search import IndexedFragment
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


def test_release_image_loads_bundled_model_without_network(monkeypatch):
    factory = Mock(return_value=model_stub())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    monkeypatch.setattr(Path, "is_dir", lambda directory: str(directory) == "/opt/embedding-model")
    get_embedder()
    factory.assert_called_once_with(
        "/opt/embedding-model", device="cpu", local_files_only=True, trust_remote_code=False,
    )


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
    fragments = (IndexedFragment(1, 10, "Заголовок", "Текст", tuple(vector())),)
    repository.list_search_fragments.return_value = fragments
    index = Mock()
    index.prepare_query.return_value = "защитить трек"
    index.texts.words.return_value = ["защитить", "трек"]
    index.search.return_value = [SearchHit(SearchChunk(1, 10, "Текст"), 0.9)]
    session = Mock(spec=Session)
    factory = Mock(return_value=embedder)
    monkeypatch.setattr(embedding_search, "get_embedder", factory)
    monkeypatch.setattr(embedding_search, "get_search_index", lambda actual: index if actual == fragments else None)
    monkeypatch.setattr("backend.content_repository.ContentSearchRepository", lambda actual: repository)
    result = embedding_search.search_embeddings("защитить трек", session=session, limit=3)
    assert [hit.chunk.content_item_id for hit in result] == [10]
    embedder.encode_query.assert_called_once_with("защитить трек")
    embedder.encode_documents.assert_not_called()
    repository.list_search_fragments.assert_called_once_with()
    index.search.assert_called_once_with("защитить трек", vector(), 3, 0.40)
    session.commit.assert_not_called()


@pytest.mark.parametrize("query,limit", [(" ", 10), ("Запрос", 0), ("Запрос", 101)])
def test_invalid_search_does_not_access_database_or_model(monkeypatch, query, limit):
    factory = Mock()
    monkeypatch.setattr(embedding_search, "get_embedder", factory)
    with pytest.raises(ValueError):
        embedding_search.search_embeddings(query, limit=limit)
    factory.assert_not_called()


@pytest.mark.parametrize("hits,metadata,expected", [
    ([SearchHit(SearchChunk(8, 2, "Найденный абзац"), 0.8)],
     [SimpleNamespace(id=2, title="Заголовок", summary="Описание")],
     [{"article_id": "2", "title": "Заголовок", "body": "Описание", "summary": "Описание"}]),
    ([], [], []),
    ([SearchHit(SearchChunk(8, 2, "Скрытый материал"), 0.8)], [],
     []),
    ([SearchHit(SearchChunk(8, 2, "Первый"), 0.8), SearchHit(SearchChunk(9, 2, "Второй"), 0.7),
      SearchHit(SearchChunk(10, 3, "Третий"), 0.6)],
     [SimpleNamespace(id=3, title="Другой", summary=None), SimpleNamespace(id=2, title="Заголовок", summary="Описание")],
     [{"article_id": "2", "title": "Заголовок", "body": "Описание", "summary": "Описание"},
      {"article_id": "3", "title": "Другой", "body": "", "summary": None}]),
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
    assert public.search(session, query="Запрос") == []
    session.execute.assert_not_called()


def test_disabled_embeddings_search_uses_bm25_without_model(monkeypatch):
    from backend.config import get_settings

    monkeypatch.setenv("EMBEDDINGS_ENABLED", "false")
    get_settings.cache_clear()
    factory = Mock(side_effect=AssertionError("Model must not load"))
    monkeypatch.setattr(embedding_search, "get_embedder", factory)
    repository = Mock()
    repository.list_chunks.return_value = [SearchChunk(1, 7, "Защита музыки")]
    monkeypatch.setattr("backend.content_repository.ContentSearchRepository", lambda session: repository)
    try:
        hits = embedding_search.search_embeddings("музыка", session=Mock())
        assert [hit.chunk.content_item_id for hit in hits] == [7]
        assert embedding_search.search_embeddings("космос", session=Mock()) == []
        factory.assert_not_called()
        repository.list_search_fragments.assert_not_called()
    finally:
        get_settings.cache_clear()
