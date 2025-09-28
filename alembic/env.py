# alembic/env.py
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

# ensure project root on sys.path (.../alembic -> project root)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import engine_from_config, pool  # noqa: E402

from alembic import context  # noqa: E402  # type: ignore[attr-defined]
from app.models import metadata as target_metadata  # noqa: E402

config = context.config

# prefer ALEMBIC_SQLITE_URL (for schema_snapshot), otherwise DATABASE_URL
env_url = os.getenv("ALEMBIC_SQLITE_URL") or os.getenv("DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

# logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no Engine, just a URL)."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No sqlalchemy.url configured for offline migrations.")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=False,
        render_as_batch=True,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with Engine/Connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
            render_as_batch=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


print("ALEMBIC URL =>", config.get_main_option("sqlalchemy.url"))

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
