"""Add the procedures described in the fee calculator specification."""
from alembic import op
import sqlalchemy as sa

revision = "0009_fee_procedures"
down_revision = "0009_merge_search_main"
branch_labels = None
depends_on = None

# Keep migration data independent of future application rule changes.
PROCEDURES = [
    ("trademark_registration", "Регистрация товарного знака"),
    ("trademark_renewal", "Продление срока действия товарного знака"),
    ("copyright_registration", "Регистрация авторского права"),
    ("property_claim", "Имущественный иск"),
    ("non_property_claim", "Неимущественный иск"),
    ("rospatent_challenge", "Оспаривание решения Роспатента"),
    ("appeal", "Апелляционная жалоба"),
    ("cassation", "Кассационная жалоба"),
    ("repeat_cassation", "Повторная кассационная жалоба"),
]


def upgrade() -> None:
    for code, name in PROCEDURES:
        op.execute(sa.text(
            "INSERT INTO application_types (code, name, description) "
            "VALUES (:code, :name, :description) ON CONFLICT (code) DO NOTHING"
        ).bindparams(code=code, name=name, description="Формула из документа «Калькулятор пошлин.docx»"))


def downgrade() -> None:
    # These are business records: keep them and any saved calculations/rates
    # referencing them rather than deleting user data on a code rollback.
    pass
