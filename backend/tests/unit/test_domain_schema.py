import io
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import configure_mappers

from backend.models import Base, ContentItem, ContentItemChunk, ContentItemTag, ContentTag


def test_domain_tables_and_fields_match_the_provided_diagram() -> None:
    diagram = (Path(__file__).resolve().parents[3] / "docs/schema.mmd").read_text()
    entities = re.findall(r"^    ([A-Z_]+) \{\n(.*?)^    \}", diagram, re.M | re.S)
    expected = {
        name.lower(): {line.split()[1] for line in fields.splitlines() if line.strip()}
        for name, fields in entities
    }
    domain_tables = {name: table for name, table in Base.metadata.tables.items()
                     if name not in {"documents", "document_chunks", "admin_sessions"}}
    assert domain_tables.keys() == expected.keys()
    for name, table in domain_tables.items():
        assert set(table.c.keys()) == expected[name], name


def test_relationships_can_be_used_as_python_objects() -> None:
    configure_mappers()
    content = ContentItem(title="Название", slug="test", type="article")
    chunk = ContentItemChunk(chunk_index=0, body="Текст")
    tag = ContentTag(name="Тег", slug="tag")
    content.chunks.append(chunk)
    content.tag_links.append(ContentItemTag(tag=tag))
    assert chunk.content_item is content
    assert content.tag_links[0].tag is tag
    assert tag.content_links[0].content_item is content


def test_migration_is_offline_and_preserves_legacy_tables() -> None:
    buffer = io.StringIO()
    config = Config("alembic.ini", output_buffer=buffer)
    command.upgrade(config, "head", sql=True)
    sql = buffer.getvalue()
    assert sql.count("CREATE TABLE ") == 29  # 24 domain, 2 legacy, admin_sessions, alembic_version
    assert "VECTOR(1024)" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "GENERATED ALWAYS AS (to_tsvector('russian'::regconfig, body)) STORED" in sql
    assert "NEW.embedding = NULL" in sql
    assert "DROP TABLE" not in sql

    buffer.seek(0)
    buffer.truncate()
    command.downgrade(config, "0002_domain_schema:0001_initial", sql=True)
    downgrade_sql = buffer.getvalue()
    assert "DROP TABLE documents;" not in downgrade_sql
    assert "DROP TABLE document_chunks;" not in downgrade_sql
