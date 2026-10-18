import pytest

from ml.bm25 import Bm25Index
from ml.preprocessing import QueryPreprocessor, RUSSIAN_STOPWORDS, normalize_text, words
from ml.tfidf import SearchChunk


def preprocessor(vocabulary):
    return QueryPreprocessor(vocabulary, Bm25Index([], stopwords=RUSSIAN_STOPWORDS).terms)


def test_library_stopwords_are_removed_from_documents_and_queries():
    index = Bm25Index([SearchChunk(1, 10, "Пожалуйста, можно ли получить компенсацию?"),
                       SearchChunk(2, 20, "Использование фонограммы")], stopwords=RUSSIAN_STOPWORDS)
    assert index.terms("Пожалуйста можно ли компенсацию") == index.terms("компенсацию")
    assert index.search("Пожалуйста можно ли компенсацию") == index.search("компенсацию")
    assert "пожалуйста" not in index.words(index.chunks[0].body)
    assert index.search("пожалуйста можно ли") == []
    assert Bm25Index([SearchChunk(1, 10, "пожалуйста можно ли")], stopwords=RUSSIAN_STOPWORDS).search("право") == []


def test_legal_negations_dates_and_law_references_remain_searchable():
    index = Bm25Index([], stopwords=RUSSIAN_STOPWORDS)
    assert {"не", "ни", "нет", "без", "нельзя", "до", "после", "перед"} <= set(index.words("не ни нет без нельзя до после перед"))
    assert index.terms("использование без лицензии") != index.terms("использование с лицензией")
    assert index.words("статья 1 закона 152‑ФЗ") == ["статья", "1", "закона", "152-фз"]


def test_normalization_handles_unicode_case_html_and_yo_consistently():
    assert normalize_text("  ПРИЁМ&nbsp;  по\n152‑ФЗ ") == "прием по 152-фз"
    assert words("ISRC, １５２-ФЗ; ёлка") == ["isrc", "152-фз", "елка"]


@pytest.mark.parametrize("typo,expected", [
    ("натариуса", "нотариуса"), ("афторские", "авторские"),
    ("догоовр", "договор"), ("компинсации", "компенсации"),
])
def test_unique_close_corpus_word_corrects_typo(typo, expected):
    processor = preprocessor([expected, "запись", "лицензия"])
    assert processor.prepare(typo) == expected


def test_known_word_forms_ambiguous_typos_and_unknown_terms_are_not_rewritten():
    processor = preprocessor(["каша", "кара", "договор", "запись"])
    assert processor.prepare("Кама") == "Кама"
    assert processor.prepare("Договорами") == "Договорами"
    assert processor.prepare("квантовая механика") == "квантовая механика"


def test_query_preserves_negation_case_acronyms_and_sentence_structure():
    processor = preprocessor(["авторские", "права", "договор"])
    assert processor.prepare("  Афторские\nправа НЕ переданы БЕЗ ISRC и 152‑ФЗ? ") == "Авторские права НЕ переданы БЕЗ ISRC и 152-ФЗ?"
    assert processor.prepare("АФТОРСКИЕ права") == "АВТОРСКИЕ права"
    assert processor.prepare("нельзя до после перед") == "нельзя до после перед"


def test_misspelled_stopwords_are_corrected_before_lexical_filtering():
    processor = preprocessor(["запись", "песни"])
    query = processor.prepare("кагда можна использовать запись")
    assert query == "когда можно использовать запись"
    assert Bm25Index([], stopwords=RUSSIAN_STOPWORDS).words(query) == ["использовать", "запись"]
