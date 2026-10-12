from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import ContentItem, ContentItemChunk, ContentStatus
from ml.embeddings import validate_embedding
from ml.tfidf import SearchChunk, SearchHit


class ContentSearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _published():
        return (
            ContentItem.status == ContentStatus.PUBLISHED,
            ContentItem.published_at <= func.now(),
        )

    def list_chunks(self) -> list[SearchChunk]:
        statement = (
            select(ContentItemChunk.id, ContentItemChunk.content_item_id, ContentItemChunk.body)
            .join(ContentItem).where(*self._published()).order_by(ContentItemChunk.id)
        )
        return [SearchChunk(*row) for row in self.session.execute(statement)]

    def nearest(self, embedding: list[float], limit: int = 10) -> list[SearchHit]:
        validate_embedding(embedding)
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        distance = ContentItemChunk.embedding.cosine_distance(embedding)
        statement = (
            select(
                ContentItemChunk.id, ContentItemChunk.content_item_id,
                ContentItemChunk.body, distance.label("distance"),
            )
            .join(ContentItem)
            .where(*self._published(), ContentItemChunk.embedding.is_not(None))
            .order_by(distance).limit(limit)
        )
        return [
            SearchHit(SearchChunk(row.id, row.content_item_id, row.body), 1 - float(row.distance))
            for row in self.session.execute(statement)
        ]
