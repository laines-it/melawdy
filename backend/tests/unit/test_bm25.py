"""BM25 checks on synthetic text only; no repositories, API, or database."""
import math

import pytest

from ml.bm25 import Bm25Index
from ml.tfidf import SearchChunk


def test_bm25_finds_relevant_chunks_and_ignores_unknown_terms() -> None:
    chunk = SearchChunk(1, 10, "авторское право музыкальное произведение")
    index = Bm25Index([
        chunk,
        SearchChunk(2, 20, "товарный знак регистрация заявки"),
        SearchChunk(3, 20, "регистрация товарного знака"),
    ])

    hits = index.search("авторское право")
    assert [hit.chunk.id for hit in hits] == [1]
    assert hits[0].chunk is chunk
    assert hits[0].score > 0
    assert index.search("несуществующийтермин") == []
    assert index.search("!!!") == []
    assert index.search("авторское несуществующийтермин") == index.search("авторское")
    assert index.search("авторское право") == hits


def test_bm25_normalizes_case_yo_and_russian_word_forms() -> None:
    index = Bm25Index([
        SearchChunk(1, 10, "Приём заявления по договору"),
        SearchChunk(2, 20, "Регистрация товарного знака"),
    ])

    assert [hit.chunk.id for hit in index.search("ПРИЕМ заявлений ДОГОВОРЫ")] == [1]
    for query in ["ПРИЕМ", "приём", "ДОГОВОРЫ", "договорами", "заявления"]:
        assert [hit.chunk.id for hit in index.search(query)] == [1]
    assert index.search("приём") == index.search("ПРИЕМ")
    assert index.search("договор") == index.search("договорами")


def test_bm25_preserves_single_digit_numbers_and_hyphenated_law_references() -> None:
    index = Bm25Index([
        SearchChunk(1, 10, "статья 1 закон 152-ФЗ"),
        SearchChunk(2, 20, "статья 2 закон 15-ФЗ"),
    ])

    assert [hit.chunk.id for hit in index.search("1")] == [1]
    assert [hit.chunk.id for hit in index.search("2")] == [2]
    assert [hit.chunk.id for hit in index.search("152-фз")] == [1]
    assert [hit.chunk.id for hit in index.search("15‑ФЗ")] == [2]
    assert index.search("152") == []  # The reference is indexed as one token.


def test_bm25_scores_follow_lucene_term_frequency_and_length_normalization() -> None:
    index = Bm25Index([
        SearchChunk(1, 10, "кот кот пес"),
        SearchChunk(2, 20, "кот"),
        SearchChunk(3, 30, "пес"),
    ], k1=1.5, b=0.75)

    hits = index.search("кот")
    # Three documents, two containing the term, average length = 5/3.
    idf = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    expected = {
        1: idf * 2 / (2 + 1.5 * (1 - 0.75 + 0.75 * 3 / (5 / 3))),
        2: idf / (1 + 1.5 * (1 - 0.75 + 0.75 * 1 / (5 / 3))),
    }
    assert [hit.chunk.id for hit in hits] == [2, 1]
    for hit in hits:
        assert hit.score == pytest.approx(expected[hit.chunk.id], rel=1e-6)


def test_bm25_can_disable_length_normalization() -> None:
    chunks = [SearchChunk(1, 10, "кот кот пес"), SearchChunk(2, 20, "кот")]
    hits = Bm25Index(chunks, k1=1.5, b=0).search("кот")

    assert [hit.chunk.id for hit in hits] == [1, 2]


def test_bm25_applies_limit_and_breaks_ties_by_chunk_id() -> None:
    index = Bm25Index([
        SearchChunk(3, 30, "договор"),
        SearchChunk(1, 10, "договор"),
        SearchChunk(2, 20, "договор"),
        SearchChunk(4, 40, "музыка"),
    ])

    assert [hit.chunk.id for hit in index.search("договор", limit=2)] == [1, 2]
    assert [hit.chunk.id for hit in index.search("договор", limit=100)] == [1, 2, 3]


@pytest.mark.parametrize("bodies", [[], [""], ["!!!"], ["", "!!!"]])
def test_bm25_handles_empty_corpora(bodies: list[str]) -> None:
    chunks = [SearchChunk(i, i, body) for i, body in enumerate(bodies)]
    assert Bm25Index(chunks).search("договор") == []


def test_bm25_handles_empty_chunks_alongside_searchable_text() -> None:
    index = Bm25Index([SearchChunk(1, 10, "!!!"), SearchChunk(2, 20, "договор")])
    assert [hit.chunk.id for hit in index.search("договор")] == [2]


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_bm25_rejects_blank_queries_even_with_empty_corpus(query: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        Bm25Index([]).search(query)


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_bm25_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="Limit"):
        Bm25Index([]).search("договор", limit=limit)


@pytest.mark.parametrize("k1", [0, -1, float("nan"), float("inf")])
def test_bm25_rejects_invalid_k1(k1: float) -> None:
    with pytest.raises(ValueError, match="k1"):
        Bm25Index([], k1=k1)


@pytest.mark.parametrize("b", [-0.1, 1.1, float("nan"), float("inf")])
def test_bm25_rejects_invalid_b(b: float) -> None:
    with pytest.raises(ValueError, match="b must"):
        Bm25Index([], b=b)
