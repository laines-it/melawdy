"""Store contextual search fragments separately from article content."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

revision = "0008_search_fragments"
down_revision = "0007_e5_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_search_indexes",
        sa.Column("content_item_id", sa.BigInteger(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
    )
    op.create_table(
        "content_search_fragments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("content_item_id", sa.BigInteger(), sa.ForeignKey("content_search_indexes.content_item_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.UniqueConstraint("content_item_id", "position"),
        sa.CheckConstraint("position >= 0", name="position_nonnegative"),
        sa.CheckConstraint("btrim(body) <> ''", name="body_not_blank"),
    )
    op.create_index("ix_content_search_fragments_content_item_id", "content_search_fragments", ["content_item_id"])
    op.execute("""
        CREATE FUNCTION invalidate_content_search() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME = 'content_items' THEN
                IF OLD.title IS DISTINCT FROM NEW.title THEN
                    DELETE FROM content_search_indexes WHERE content_item_id = NEW.id;
                END IF;
            ELSE
                IF TG_OP <> 'INSERT' THEN
                    DELETE FROM content_search_indexes WHERE content_item_id = OLD.content_item_id;
                END IF;
                IF TG_OP <> 'DELETE' THEN
                    DELETE FROM content_search_indexes WHERE content_item_id = NEW.content_item_id;
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER tr_content_search_title AFTER UPDATE OF title ON content_items
        FOR EACH ROW EXECUTE FUNCTION invalidate_content_search();
        CREATE TRIGGER tr_content_search_chunks AFTER INSERT OR DELETE OR UPDATE OF body, chunk_index, content_item_id
        ON content_item_chunks FOR EACH ROW EXECUTE FUNCTION invalidate_content_search();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER tr_content_search_chunks ON content_item_chunks")
    op.execute("DROP TRIGGER tr_content_search_title ON content_items")
    op.execute("DROP FUNCTION invalidate_content_search()")
    op.drop_table("content_search_fragments")
    op.drop_table("content_search_indexes")
