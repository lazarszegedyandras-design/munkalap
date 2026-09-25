import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context
from app.database import Base
from app import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.config import get_settings

database_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        migration_role = os.getenv("MIGRATION_SET_ROLE", "").strip()
        if migration_role and migration_role != "workapp_owner":
            raise RuntimeError("MIGRATION_SET_ROLE must be workapp_owner")

        context.configure(connection=connection, target_metadata=target_metadata)

        # IMPORTANT: SET ROLE must execute inside the transaction that Alembic
        # owns. With SQLAlchemy 2.x, executing SET ROLE before
        # context.begin_transaction() triggers an implicit/autobegin
        # transaction. Alembic then runs inside that already-open transaction
        # without owning its commit; when the connection is closed, SQLAlchemy
        # rolls the migration DDL and alembic_version update back. The log still
        # looks like every revision ran, but the schema remains unchanged.
        with context.begin_transaction():
            if migration_role:
                connection.execute(text("SET ROLE workapp_owner"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
