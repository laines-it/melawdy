"""Join existing main and search migration histories."""

revision = "0009_merge_search_main"
down_revision = ("0008_template_constructor", "0008_search_fragments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
