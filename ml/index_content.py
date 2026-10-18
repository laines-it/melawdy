import argparse

from sqlalchemy import func, select, update

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models import ContentItemChunk
from ml.embeddings import get_embedder


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute embeddings for content chunks")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="Recompute all embeddings")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 128:
        parser.error("batch-size must be between 1 and 128")
    settings = get_settings()
    embedder = None
    last_id = 0
    indexed = 0
    with SessionLocal() as session:
        while True:
            statement = (
                select(ContentItemChunk.id, ContentItemChunk.body, ContentItemChunk.updated_at)
                .where(ContentItemChunk.id > last_id).order_by(ContentItemChunk.id)
                .limit(args.batch_size)
            )
            if not args.force:
                statement = statement.where(ContentItemChunk.embedding.is_(None))
            rows = session.execute(statement).all()
            if not rows:
                break
            if embedder is None:
                print("Loading embedding model", flush=True)
                embedder = get_embedder(settings.embedding_model_path, settings.embedding_device)
            vectors = embedder.encode_documents([row.body for row in rows])
            for row, vector in zip(rows, vectors, strict=True):
                result = session.execute(
                    update(ContentItemChunk)
                    .where(ContentItemChunk.id == row.id, ContentItemChunk.updated_at == row.updated_at,
                           ContentItemChunk.body == row.body)
                    .values(embedding=vector)
                )
                indexed += result.rowcount
            session.commit()
            last_id = rows[-1].id
            print(f"Indexed {indexed} chunks; last chunk id: {last_id}", flush=True)
        missing = session.scalar(select(func.count()).select_from(ContentItemChunk)
                                 .where(ContentItemChunk.embedding.is_(None)))
        if missing:
            raise RuntimeError(f"{missing} chunks still lack embeddings; rerun indexing after concurrent edits")
    print(f"Index ready: {indexed} chunks calculated; no missing embeddings", flush=True)


if __name__ == "__main__":
    main()
