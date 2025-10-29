# alembic/env.py
from __future__ import annotations

import os
from logging import config as log_config  # for fileConfig
from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool
from alembic import context  # ✅ correct import

# ---- Alembic Config & logging -------------------------------------------------
config = context.config
if config and config.config_filepath:
    fileConfig(config.config_file_name)  # keep alembic.ini logging

# ---- Load project metadata (scan app.models) ----------------------------------
from app.db.base import Base, init_models  # type: ignore

# Proactively load all SQLAlchemy models under app.models into Base.metadata
init_models()
target_metadata = Base.metadata


def _resolve_url() -> str:
    """
    Resolve DB URL in order:
      1) env: DATABASE_URL
      2) alembic.ini -> sqlalchemy.url
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DATABASE_URL or sqlalchemy.url configured for Alembic")
    return url


def _include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """
    Autogenerate filter:
      * If an object exists only in DB (reflected=True) and not in metadata (compare_to is None),
        skip generating DROP statements to avoid accidental destructive diffs.
    """
    if reflected and compare_to is None and type_ in {"table", "index", "unique_constraint", "foreign_key_constraint"}:
        return false
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    ini = dict(config.get_section(config.config_ini_section) or {})
    ini["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(
        ini,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=False,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
