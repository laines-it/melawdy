"""Resize embeddings for E5 and invalidate incompatible vectors."""
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision = "0007_e5_embeddings"
down_revision = "0006_user_favorites"
branch_labels = None
depends_on = None


def _resize(dimensions: int) -> None:
    op.drop_index("ix_content_item_chunks_embedding", table_name="content_item_chunks")
    op.alter_column(
        "content_item_chunks", "embedding", type_=VECTOR(dimensions),
        postgresql_using=f"NULL::vector({dimensions})",
    )
    op.create_index(
        "ix_content_item_chunks_embedding", "content_item_chunks", ["embedding"],
        postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    _resize(384)


def downgrade() -> None:
    _resize(1024)
