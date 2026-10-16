from alembic import op
import sqlalchemy as sa

revision = "0007_login_attempt_window"
down_revision = "0006_user_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_failed_login_at")