from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend.content_repository import ContentSearchRepository
from ml.constants import EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, PASSAGE_PREFIX, QUERY_PREFIX
from ml.embeddings import LegalEmbedder, get_embedder, validate_embedding
from ml.tfidf import SearchChunk, SearchHit, TfidfIndex, reciprocal_rank_fusion


def test_tfidf_finds_relevant_chunks_and_handles_unknown_queries() -> None:
    index = TfidfIndex([
        SearchChunk(1, 10, "авторское право музыкальное произведение"),
        SearchChunk(2, 20, "товарный знак регистрация заявки"),
        SearchChunk(3, 20, "регистрация товарного знака"),
    ])
    hits = index.search("авторское право")
    assert [hit.chunk.id for hit in hits] == [1]
    assert hits[0].score > 0
    assert index.search("несуществующийтермин") == []
    assert len(index.search("регистрация", limit=1)) == 1


def test_tfidf_preserves_single_digit_article_numbers() -> None:
    index = TfidfIndex([SearchChunk(1, 10, "статья 1"), SearchChunk(2, 10, "статья 2")])
    assert index.search("2")[0].chunk.id == 2


@pytest.mark.parametrize("chunks", [[], [SearchChunk(1, 10, "!!!")]])
def test_tfidf_handles_empty_corpus(chunks: list[SearchChunk]) -> None:
    assert TfidfIndex(chunks).search("право") == []


def test_rank_fusion_deduplicates_chunks_and_rewards_agreement() -> None:
    first, second, third = (SearchChunk(i, i, str(i)) for i in range(1, 4))
    hits = reciprocal_rank_fusion(
        [SearchHit(first, 0.9), SearchHit(second, 0.5)],
        [SearchHit(third, 0.8), SearchHit(second, 0.2)],
    )
    assert hits[0].chunk is second
    assert len({hit.chunk.id for hit in hits}) == 3


def make_model() -> Mock:
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = EMBEDDING_DIMENSIONS
    model.tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    model.encode.return_value = [[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)]
    return model


def test_query_prefix_and_document_encoding_follow_model_contract() -> None:
    model = make_model()
    embedder = LegalEmbedder(model)
    assert len(embedder.encode_query(" авторское право ")) == EMBEDDING_DIMENSIONS
    assert model.encode.call_args.args[0] == [QUERY_PREFIX + "авторское право"]
    assert model.encode.call_args.kwargs["normalize_embeddings"] is True
    assert model.max_seq_length == EMBEDDING_MAX_TOKENS
    embedder.encode_documents(["Текст документа"])
    assert model.encode.call_args.args[0] == [PASSAGE_PREFIX + "Текст документа"]


def test_long_chunks_are_rejected_instead_of_silently_truncated() -> None:
    model = make_model()
    model.tokenizer.return_value = {"input_ids": [[1] * (EMBEDDING_MAX_TOKENS + 1)]}
    with pytest.raises(ValueError, match="512"):
        LegalEmbedder(model).encode_documents(["Длинный текст"])
    model.encode.assert_not_called()


def test_missing_model_directory_does_not_trigger_a_download(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="EMBEDDING_MODEL_PATH"):
        get_embedder(str(tmp_path / "missing-model"))


@pytest.mark.parametrize("vector", [[], [0.0] * EMBEDDING_DIMENSIONS,
                                    [float("nan")] * EMBEDDING_DIMENSIONS])
def test_invalid_vectors_are_rejected_before_database_access(vector: list[float]) -> None:
    session = Mock(spec=Session)
    with pytest.raises(ValueError):
        ContentSearchRepository(session).nearest(vector)
    session.execute.assert_not_called()


def test_vector_search_filters_out_unpublished_content() -> None:
    session = Mock(spec=Session)
    session.execute.return_value = [SimpleNamespace(
        id=1, content_item_id=10, body="Текст", distance=0.25
    )]
    vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    validate_embedding(vector)
    hits = ContentSearchRepository(session).nearest(vector)
    assert hits[0].score == 0.75
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "content_items.status = 'published'" in sql
    assert "content_items.published_at <= now()" in sql
    assert "embedding IS NOT NULL" in sql
    assert "<=>" in sql
