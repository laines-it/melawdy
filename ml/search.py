import argparse
import json

from backend.config import get_settings
from backend.content_repository import ContentSearchRepository
from backend.db import SessionLocal
from ml.embeddings import get_embedder
from ml.embedding_search import search_embeddings
from ml.tfidf import TfidfIndex


def main() -> None:
    parser = argparse.ArgumentParser(description="Search published MeLawDy content")
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", choices=["tfidf", "embedding", "hybrid"], default="hybrid")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.query.strip() or not 1 <= args.limit <= 100:
        parser.error("query must not be blank and limit must be between 1 and 100")
    with SessionLocal() as session:
        repository = ContentSearchRepository(session)
        if args.mode == "hybrid":
            hits = search_embeddings(args.query, session=session, limit=args.limit)
        elif args.mode == "tfidf":
            hits = TfidfIndex(repository.list_chunks()).search(args.query, args.limit)
        else:
            settings = get_settings()
            embedder = get_embedder(settings.embedding_model_path, settings.embedding_device)
            hits = repository.nearest(embedder.encode_query(args.query), args.limit)
    print(json.dumps([
        {"chunk_id": hit.chunk.id, "content_item_id": hit.chunk.content_item_id,
         "body": hit.chunk.body, "score": hit.score} for hit in hits
    ], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
