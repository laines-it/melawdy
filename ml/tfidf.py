from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


@dataclass(frozen=True)
class SearchChunk:
    id: int
    content_item_id: int
    body: str


@dataclass(frozen=True)
class SearchHit:
    chunk: SearchChunk
    score: float


class TfidfIndex:
    """An in-process index; rebuild it when the published corpus changes."""

    def __init__(self, chunks: Sequence[SearchChunk]) -> None:
        self.chunks = tuple(chunks)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, norm="l2", dtype=np.float32,
            token_pattern=r"(?u)\b\w+\b",
        )
        analyzer = self.vectorizer.build_analyzer()
        self.matrix = (
            self.vectorizer.fit_transform([chunk.body for chunk in self.chunks])
            if any(analyzer(chunk.body) for chunk in self.chunks) else None
        )

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not query.strip():
            raise ValueError("Query must not be blank")
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        if self.matrix is None:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = linear_kernel(query_vector, self.matrix).ravel()
        ranked = sorted(
            (index for index, score in enumerate(scores) if score > 0),
            key=lambda index: (-float(scores[index]), self.chunks[index].id),
        )[:limit]
        return [SearchHit(self.chunks[index], float(scores[index])) for index in ranked]


def reciprocal_rank_fusion(*rankings: Sequence[SearchHit], limit: int = 10) -> list[SearchHit]:
    """Combine ranks because TF-IDF and vector scores have different scales."""
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    chunks: dict[int, SearchChunk] = {}
    scores: dict[int, float] = {}
    for ranking in rankings:
        seen: set[int] = set()
        for rank, hit in enumerate(ranking, start=1):
            if hit.chunk.id in seen:
                continue
            seen.add(hit.chunk.id)
            chunks[hit.chunk.id] = hit.chunk
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1 / (60 + rank)
    ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return [SearchHit(chunks[chunk_id], scores[chunk_id]) for chunk_id in ids]
