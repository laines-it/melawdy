from typing import TYPE_CHECKING

from ml.embeddings import get_embedder
from ml.hybrid_search import get_search_index
from ml.tfidf import SearchHit

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def search_embeddings(query: str, *, session: "Session | None" = None,
                      limit: int = 10) -> list[SearchHit]:
    """Combine contextual E5 embeddings and BM25 for published articles."""
    if not query.strip():
        raise ValueError("Query must not be blank")
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    if session is None:
        from backend.db import SessionLocal

        with SessionLocal() as owned_session:
            return search_embeddings(query, session=owned_session, limit=limit)

    from backend.content_repository import ContentSearchRepository
    from backend.config import get_settings

    settings = get_settings()
    fragments = ContentSearchRepository(session).list_search_fragments()
    if not fragments:
        return []
    index = get_search_index(fragments)
    prepared = index.prepare_query(query)
    if not index.texts.words(prepared):
        return []
    vector = get_embedder(settings.embedding_model_path, settings.embedding_device).encode_query(prepared)
    return index.search(prepared, vector, limit, settings.search_min_similarity)
