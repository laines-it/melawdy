from alembic import context
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import create_engine, pool

from backend.config import get_settings
from backend.models import Base

target_metadata = Base.metadata


def include_object(value, name, kind, reflected, compare_to):
    # Existing local installations can contain this unmanaged metadata table.
    # Keep its contents outside Alembic's generated schema changes.
    return not (kind == "table" and name == "app_metadata" and reflected and compare_to is None)


def render_item(kind, value, autogen_context):
    if kind == "type" and isinstance(value, VECTOR):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.VECTOR(dim={value.dim!r})"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True,
            render_item=render_item, include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
