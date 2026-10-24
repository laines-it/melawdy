"""Store the fee calculator decision tree."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_fee_catalog"
down_revision = "0010_backfill_content_item_slugs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fee_catalogs",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("source_json", JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fee_catalogs")
