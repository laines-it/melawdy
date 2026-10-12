"""Run in CI after 0001, before upgrading to the domain schema."""
from uuid import UUID

from backend.db import SessionLocal
from backend.models import Document, DocumentChunk

DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")


def main() -> None:
    with SessionLocal.begin() as session:
        document = Document(id=DOCUMENT_ID, title="Before domain migration", body="Existing data")
        document.chunks.append(DocumentChunk(text="Existing chunk", embedding=[1.0, 0.0, 0.0]))
        session.add(document)


if __name__ == "__main__":
    main()
