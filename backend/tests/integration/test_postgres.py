from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from backend.db import SessionLocal
from backend.models import Document, DocumentChunk
from backend.tests.integration.seed_legacy import DOCUMENT_ID


def test_existing_documents_survive_domain_migration() -> None:
    with SessionLocal() as session:
        document = session.get(Document, DOCUMENT_ID)
        assert document is not None
        assert document.body == "Existing data"
        assert document.chunks[0].text == "Existing chunk"
        assert list(document.chunks[0].embedding) == [1.0, 0.0, 0.0]


def test_migration_and_vector_round_trip() -> None:
    with SessionLocal() as session:
        assert session.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")) == "vector"
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        document = Document(title="Векторный пример", body="Текст")
        document.chunks.append(DocumentChunk(text="Первый фрагмент", embedding=[1.0, 0.0, 0.0]))
        session.add(document)
        session.commit()

        chunk = session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).one()
        assert list(chunk.embedding) == [1.0, 0.0, 0.0]
        assert session.scalar(
            select(DocumentChunk.embedding.l2_distance([1.0, 0.0, 0.0]))
            .where(DocumentChunk.id == chunk.id)
        ) == 0.0
