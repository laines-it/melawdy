import argparse
import json

from backend.config import get_settings
from backend.content_repository import ContentSearchRepository
from backend.db import SessionLocal
from ml.embeddings import get_embedder
from ml.tfidf import TfidfIndex, reciprocal_rank_fusion


def main() -> None:
    parser = argparse.ArgumentParser(description="Search published MeLawDy content")
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", choices=["tfidf", "embedding", "hybrid"], default="tfidf")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.query.strip() or not 1 <= args.limit <= 100:
        parser.error("query must not be blank and limit must be between 1 and 100")
    candidate_limit = min(args.limit * 3, 100) if args.mode == "hybrid" else args.limit
    rankings = []
    with SessionLocal() as session:
        repository = ContentSearchRepository(session)
        if args.mode in {"tfidf", "hybrid"}:
            rankings.append(TfidfIndex(repository.list_chunks()).search(args.query, candidate_limit))
        if args.mode in {"embedding", "hybrid"}:
            settings = get_settings()
            embedder = get_embedder(settings.embedding_model_path, settings.embedding_device)
            rankings.append(repository.nearest(embedder.encode_query(args.query), candidate_limit))
    hits = reciprocal_rank_fusion(*rankings, limit=args.limit) if len(rankings) == 2 else rankings[0]
    print(json.dumps([
        {"chunk_id": hit.chunk.id, "content_item_id": hit.chunk.content_item_id,
         "body": hit.chunk.body, "score": hit.score} for hit in hits
    ], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
