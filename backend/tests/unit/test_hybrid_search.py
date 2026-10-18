import copy
from unittest.mock import Mock

import pytest

from ml.hybrid_search import HybridSearch, IndexedFragment, get_search_index
from ml.search_documents import clean_text, prepare_documents, source_hash
from ml.constants import EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS
from ml.embeddings import LegalEmbedder


def vector(axis=0):
    return tuple(float(index == axis) for index in range(EMBEDDING_DIMENSIONS))


def test_search_text_keeps_context_and_original_source():
    bodies = ["Автор: Пример\n\n## Защита записи\n\nРегистрация не нужна.",
              "Сохраните исходники и переписку, чтобы подтвердить дату создания.",
              "Читайте также: «Чужая статья»", "«Ещё одна чужая статья».",
              "### Примечание\n\n[1] Прибыль — служебное определение из глоссария."]
    original = copy.deepcopy(bodies)
    documents = prepare_documents("Права на запись", bodies)
    assert bodies == original
    assert len(documents) == 1
    assert documents[0].startswith("Права на запись\nЗащита записи\n\n")
    assert "Регистрация не нужна." in documents[0] and "Сохраните исходники" in documents[0]
    assert all(word not in documents[0] for word in ["Пример", "чужая", "Прибыль", "Чужая"])


def test_cleaning_preserves_link_labels_and_substantive_quotes():
    assert clean_text("См. [источник](https://example.test/path) [12] и закон (https://example.test/a).") == "См. источник и закон ."
    docs = prepare_documents("Доказательства", ["«Оригинал произведения подтверждает авторство».\n\nСохраните файл. Читайте подробнее: Чужая статья"])
    assert "Оригинал произведения подтверждает авторство" in " ".join(docs)
    assert "Чужая статья" not in " ".join(docs)


def test_every_split_fragment_repeats_title_and_section():
    text = " ".join(f"Длинное предложение о записи номер {index}." for index in range(80))
    docs = prepare_documents("Название", ["## Раздел\n\n" + text])
    assert len(docs) > 2
    assert all(doc.startswith("Название\nРаздел\n\n") for doc in docs)
    assert all(len(doc.split("\n\n", 1)[1]) <= 560 for doc in docs)


def test_fingerprint_changes_with_title_body_order_and_content():
    base = source_hash("Оригинал", ["Первый", "Второй"])
    assert base == source_hash("Оригинал", ["Первый", "Второй"])
    assert len({base, source_hash("Новый", ["Первый", "Второй"]),
                source_hash("Оригинал", ["Второй", "Первый"]),
                source_hash("Оригинал", ["Изменённый", "Второй"])}) == 4


def test_exact_title_wins_over_semantically_closer_other_article():
    fragments = (IndexedFragment(1, 10, "Договор с музыкантом", "Условия договора о записи музыки", vector(1)),
                 IndexedFragment(2, 20, "Чужие права", "Договор с музыкантом упомянут здесь", vector()))
    hits = HybridSearch(fragments).search("ДОГОВОР С МУЗЫКАНТОМ!", list(vector()), limit=1)
    assert [hit.chunk.content_item_id for hit in hits] == [10]


def test_unrelated_query_is_rejected_despite_lexical_overlap():
    fragment = IndexedFragment(1, 10, "Регистрация записи", "Как зарегистрировать запись и получить документ", vector())
    assert HybridSearch((fragment,)).search("Как зарегистрировать автомобиль?", list(vector(1))) == []


def test_article_results_are_unique_and_cache_changes_with_corpus():
    fragments = (IndexedFragment(1, 10, "Договор", "Договор для автора музыки", vector()),
                 IndexedFragment(2, 10, "Договор", "Ещё один раздел договора", vector()),
                 IndexedFragment(3, 20, "Запись", "Оригинал записи произведения", vector()))
    index = get_search_index(fragments)
    assert get_search_index(fragments) is index
    hits = index.search("договор автора", list(vector()))
    assert len({hit.chunk.content_item_id for hit in hits}) == len(hits) == 2
    assert get_search_index(fragments[:1]) is not index
    assert HybridSearch(()).search("договор", list(vector())) == []


def test_context_is_kept_within_token_budget_on_every_part():
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = EMBEDDING_DIMENSIONS
    model.tokenizer.side_effect = lambda texts, **kwargs: {"input_ids": [[0] * (len(text) + 2) for text in texts]}
    embedder = LegalEmbedder(model)
    context = "Название и раздел\n\n"
    text = "Длинное предложение. " * 100
    parts = embedder.split_document(text, context=context)
    assert "".join(part.removeprefix(context) for part in parts) == text
    assert all(part.startswith(context) for part in parts)
    assert all(embedder._document_size(part) <= EMBEDDING_MAX_TOKENS for part in parts)


@pytest.mark.parametrize("query,limit", [(" ", 1), ("договор", 0), ("договор", 101)])
def test_invalid_search_is_rejected(query, limit):
    with pytest.raises(ValueError):
        HybridSearch(()).search(query, list(vector()), limit)
