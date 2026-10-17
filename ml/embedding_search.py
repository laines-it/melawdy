from typing import TYPE_CHECKING

from ml.embeddings import get_embedder
from ml.tfidf import SearchHit

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def search_embeddings(query: str, *, session: "Session | None" = None,
                      limit: int = 10) -> list[SearchHit]:
    """Rank published articles by their closest chunk using local E5 embeddings."""
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
    vector = get_embedder(settings.embedding_model_path, settings.embedding_device).encode_query(query)
    return ContentSearchRepository(session).nearest_articles(vector, limit)
