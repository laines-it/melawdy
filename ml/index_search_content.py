import argparse
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models import ContentItem, ContentItemChunk, ContentSearchIndex, ContentSearchFragment
from ml.embeddings import LegalEmbedder, get_embedder
from ml.search_documents import prepare_documents, source_hash


@dataclass(frozen=True)
class ArticleSource:
    id: int
    title: str
    bodies: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return source_hash(self.title, list(self.bodies))


def read_sources(session: Session) -> list[ArticleSource]:
    articles = session.execute(select(ContentItem.id, ContentItem.title).order_by(ContentItem.id)).all()
    bodies: dict[int, list[str]] = {}
    for aid, body in session.execute(select(ContentItemChunk.content_item_id, ContentItemChunk.body)
                                    .order_by(ContentItemChunk.content_item_id, ContentItemChunk.chunk_index)):
        bodies.setdefault(aid, []).append(body)
    return [ArticleSource(row.id, row.title, tuple(bodies.get(row.id, []))) for row in articles]


def index_articles(session_factory: Callable, embedder_factory: Callable[[], LegalEmbedder],
                   *, batch_size: int = 8, force: bool = False) -> int:
    with session_factory() as session:
        sources = read_sources(session)
        ready = dict(session.execute(select(ContentSearchIndex.content_item_id, ContentSearchIndex.source_hash)).all())
    embedder = None
    calculated = 0
    for source in sources:
        if not force and ready.get(source.id) == source.fingerprint:
            continue
        documents = prepare_documents(source.title, list(source.bodies))
        if documents and embedder is None:
            embedder = embedder_factory()
        fragments = []
        for document in documents:
            context, body = document.split("\n\n", 1)
            fragments.extend(embedder.split_document(body, context=context + "\n\n"))
        vectors = []
        for start in range(0, len(fragments), batch_size):
            vectors.extend(embedder.encode_documents(fragments[start:start + batch_size]))
        if len(vectors) != len(fragments):
            raise ValueError("The model returned an unexpected number of embeddings")
        with session_factory() as session:
            article = session.scalar(select(ContentItem).where(ContentItem.id == source.id).with_for_update())
            current = tuple(session.scalars(select(ContentItemChunk.body)
                            .where(ContentItemChunk.content_item_id == source.id)
                            .order_by(ContentItemChunk.chunk_index).with_for_update()))
            if article is None or source_hash(article.title, list(current)) != source.fingerprint:
                raise RuntimeError(f"Article {source.id} changed during indexing; retry indexing")
            session.execute(delete(ContentSearchIndex).where(ContentSearchIndex.content_item_id == source.id))
            session.add(ContentSearchIndex(content_item_id=source.id, source_hash=source.fingerprint))
            session.flush()
            session.add_all([ContentSearchFragment(content_item_id=source.id, position=position,
                             body=body, embedding=vector)
                             for position, (body, vector) in enumerate(zip(fragments, vectors, strict=True))])
            session.commit()
        calculated += len(fragments)
        print(f"Search index: article {source.id}, {len(fragments)} fragments", flush=True)
    with session_factory() as session:
        current = read_sources(session)
        ready = dict(session.execute(select(ContentSearchIndex.content_item_id, ContentSearchIndex.source_hash)).all())
        if any(ready.get(source.id) != source.fingerprint for source in current):
            raise RuntimeError("Search index changed during indexing; retry indexing")
    print(f"Search index ready: {calculated} fragments calculated", flush=True)
    return calculated


def main() -> None:
    parser = argparse.ArgumentParser(description="Build contextual search fragments")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 128:
        parser.error("batch-size must be between 1 and 128")
    settings = get_settings()
    index_articles(SessionLocal, lambda: get_embedder(settings.embedding_model_path, settings.embedding_device),
                   batch_size=args.batch_size, force=args.force)


if __name__ == "__main__":
    main()
