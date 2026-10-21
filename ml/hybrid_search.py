from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ml.bm25 import Bm25Index
from ml.search_documents import normalized_title
from ml.tfidf import SearchChunk, SearchHit
from ml.preprocessing import QueryPreprocessor, RUSSIAN_STOPWORDS, words


@dataclass(frozen=True)
class IndexedFragment:
    id: int
    content_item_id: int
    title: str
    body: str
    embedding: tuple[float, ...]


class HybridSearch:
    def __init__(self, fragments: tuple[IndexedFragment, ...]) -> None:
        self.fragments = fragments
        self.articles = {part.content_item_id: part.title for part in fragments}
        self.vectors = np.asarray([part.embedding for part in fragments], dtype=np.float32)
        if len(fragments):
            self.vectors /= np.linalg.norm(self.vectors, axis=1, keepdims=True)
        self.titles = Bm25Index([SearchChunk(aid, aid, title) for aid, title in self.articles.items()],
                                stopwords=RUSSIAN_STOPWORDS)
        self.texts = Bm25Index([SearchChunk(part.id, part.content_item_id, part.body) for part in fragments],
                               stopwords=RUSSIAN_STOPWORDS)
        self.preprocessor = QueryPreprocessor((word for part in fragments for word in words(part.body)),
                                               self.texts.terms)

    def prepare_query(self, query: str) -> str:
        return self.preprocessor.prepare(query)

    def search(self, query: str, vector: list[float], limit: int = 10,
               min_similarity: float = 0.40) -> list[SearchHit]:
        if not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Provide a nonblank query and a limit between 1 and 100")
        if not self.fragments:
            return []
        query = self.prepare_query(query)
        similarities = self.vectors @ np.asarray(vector, dtype=np.float32)
        best: dict[int, int] = {}
        for index, part in enumerate(self.fragments):
            aid = part.content_item_id
            if aid not in best or similarities[index] > similarities[best[aid]]:
                best[aid] = index
        semantic = sorted(best, key=lambda aid: (-float(similarities[best[aid]]), aid))
        lexical_query = " ".join(self.texts.words(query))
        if not lexical_query:
            return []
        lexical = []
        for hit in self.texts.search(lexical_query, 100):
            if hit.chunk.content_item_id not in lexical:
                lexical.append(hit.chunk.content_item_id)
        terms = set(self.titles.terms(lexical_query))
        titles = [hit.chunk.content_item_id for hit in self.titles.search(lexical_query, 100)
                  if terms and len(terms & set(self.titles.terms(hit.chunk.body))) / len(terms) >= 0.5]
        exact = {aid for aid, title in self.articles.items()
                 if normalized_title(title) == normalized_title(query)}
        if float(similarities[best[semantic[0]]]) < min_similarity and not exact:
            return []
        scores: dict[int, float] = {}
        for ranking in [semantic, lexical, titles]:
            for rank, aid in enumerate(ranking, start=1):
                scores[aid] = scores.get(aid, 0.0) + 1 / (20 + rank)
        ordered = sorted(best, key=lambda aid: (aid not in exact, -scores.get(aid, 0), aid))
        hits = []
        for aid in ordered:
            index = best[aid]
            if aid not in exact and similarities[index] < min_similarity:
                continue
            part = self.fragments[index]
            hits.append(SearchHit(SearchChunk(part.id, aid, part.body), scores[aid]))
        return hits[:limit]


@lru_cache(maxsize=1)
def get_search_index(fragments: tuple[IndexedFragment, ...]) -> HybridSearch:
    return HybridSearch(fragments)
