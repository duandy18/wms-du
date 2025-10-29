# alembic/env.py
from __future__ import annotations

import os
from logging import getLogger
from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool
from alembic import context

# --- logging ---
config = context.get_section(context.config.config_ini_section)
if context.config.config_file_name:
    fileConfig(context.config.config_file, disable_existing_loggers=False)
log = getLogger(__name__)

# --- load project models into metadata ---
from app.db.base import Base, init_models  # type: ignore

# 主动加载 app.models 下所有模型，避免 autogenerate 看不到
init_models()
target_metadata = Base.metadata

def _resolve_url() -> str:
    url = os.getenv("DATABASE_PER_ALEMBIC") or os.getenv("DATABASE_URL") \
          or (context.config.get_main_option("sqlalchemy.url") or "")
    if not url:
        raise RuntimeError("No DATABASE_URL/sqlalchemy.url configured for Alembic")
    return url

def _include_object(object_: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """
    避免把“仅存在于数据库、模型中没有”的对象当成删除目标。
    """
    if reflected and compare_to is None and type_ in {"table", "index", "unique_constraint", "foreign_key_constraint"}:
        # DB 有但模型里没有 → 不生成 DROP
        return False
    return True

def run_migrations_offline() -> None:
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
    ini = dict(context.config.get_section(context.config.config_ini_section) or {})
    ini["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(ini, prefix="sqlalchemy.", poolclass=pool.NullPool, future=True)
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
