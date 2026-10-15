
from alembic import op
import sqlalchemy as sa

revision = "0006_user_favorites"
down_revision = "0005_auth_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content_item_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            name=op.f("fk_user_favorites_content_item_id_content_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_favorites")),
        sa.UniqueConstraint(
            "user_id", "content_item_id", name="uq_user_favorites_user_content"
        ),
    )
    op.create_index(
        op.f("ix_user_favorites_user_id"), "user_favorites", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_favorites_content_item_id"),
        "user_favorites",
        ["content_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_favorites_content_item_id"), table_name="user_favorites")
    op.drop_index(op.f("ix_user_favorites_user_id"), table_name="user_favorites")
    op.drop_table("user_favorites")