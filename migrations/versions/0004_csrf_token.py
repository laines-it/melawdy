from alembic import op
import sqlalchemy as sa

revision = "0004_csrf_token"
down_revision = "0003_admin_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_sessions",
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False, server_default="")
    )
    # Убираем server_default после заполнения существующих строк (если они есть)
    op.alter_column(
        "admin_sessions",
        "csrf_token_hash",
        server_default=None
    )


def downgrade() -> None:
    op.drop_column("admin_sessions", "csrf_token_hash")