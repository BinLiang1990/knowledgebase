from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from kb_backend.config import get_settings
from kb_backend.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The real DB URL comes from Settings (env vars / .env), never from alembic.ini.
# NOTE: deliberately NOT using config.set_main_option("sqlalchemy.url", ...) /
# engine_from_config() here — both round-trip the URL through configparser,
# whose interpolation treats a bare "%" as its own syntax. A URL-encoded
# special character in the password (e.g. "!" -> "%21") then raises
# `ValueError: invalid interpolation syntax`. Building the engine directly
# from the Settings-provided URL string sidesteps configparser entirely.
DATABASE_URL = get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no live DB connection)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
