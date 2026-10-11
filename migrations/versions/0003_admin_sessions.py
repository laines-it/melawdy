"""Store revocable admin sessions without storing raw session cookies."""
from alembic import op
import sqlalchemy as sa

revision = "0003_admin_sessions"
down_revision = "0002_domain_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_admin_sessions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash", name="pk_admin_sessions"),
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("admin_sessions")
