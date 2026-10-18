from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_template_constructor"
down_revision = "0007_login_attempt_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_templates",
        sa.Column(
            "schema_json",
            JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "document_templates",
        sa.Column(
            "structure_json",
            JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_templates", "structure_json")
    op.drop_column("document_templates", "schema_json")