"""In-process BM25 search over a caller-supplied corpus, without database access."""
from collections.abc import Collection, Sequence
import math

import bm25s
from bm25s.tokenization import Tokenizer
import Stemmer

from ml.tfidf import SearchChunk, SearchHit
from ml.preprocessing import normalize_text, words


class Bm25Index:
    """Lucene BM25 with Russian stemming and reusable corpus statistics."""

    def __init__(self, chunks: Sequence[SearchChunk], *, k1: float = 1.5, b: float = 0.75,
                 stopwords: Collection[str] = ()) -> None:
        if not math.isfinite(k1) or k1 <= 0:
            raise ValueError("k1 must be finite and greater than zero")
        if not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("b must be finite and between zero and one")

        self.chunks = tuple(chunks)
        self.stopwords = frozenset(normalize_text(word) for word in stopwords)
        self._stemmer = Stemmer.Stemmer("russian")
        tokenizer = Tokenizer(
            lower=False, splitter=self.words,
            stopwords=[], stemmer=self._stemmer,
        )
        self._index = None
        self._vocab = {}
        if not self.chunks:
            return
        tokens = tokenizer.tokenize(
            [normalize_text(chunk.body) for chunk in self.chunks],
            update_vocab=True, return_as="tuple", show_progress=False, allow_empty=False,
        )
        if any(tokens.ids):
            self._vocab = tokens.vocab.copy()
            self._index = bm25s.BM25(k1=k1, b=b, method="lucene")
            self._index.index(tokens, show_progress=False)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not query.strip():
            raise ValueError("Query must not be blank")
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        if self._index is None:
            return []
        stems = self.terms(query)
        tokens = [self._vocab[stem] for stem in stems if stem in self._vocab]
        if not tokens:
            return []
        scores = self._index.get_scores(tokens)
        ranked = sorted(
            (index for index, score in enumerate(scores) if score > 0),
            key=lambda index: (-float(scores[index]), self.chunks[index].id),
        )[:limit]
        return [SearchHit(self.chunks[index], float(scores[index])) for index in ranked]

    def terms(self, text: str) -> list[str]:
        return self._stemmer.stemWords(self.words(text))

    def words(self, text: str) -> list[str]:
        return [word for word in words(text) if word not in self.stopwords]
