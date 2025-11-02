# alembic/env.py
from __future__ import annotations

import os
import re
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

# ---- Alembic Config & logging ------------------------------------------------
config = context.config
if config and config.config_file_name:
    fileConfig(config.config_file_name)

# ---- Load project metadata (scan app.models) ---------------------------------
# 维持你原有的做法：初始化并收集 Base.metadata
from app.db.base import Base, init_models  # type: ignore

init_models()
target_metadata = Base.metadata


# ---- Helpers -----------------------------------------------------------------
_ASYNCPG_RE = re.compile(r"\+asyncpg\b", flags=re.IGNORECASE)


def _sync_url(url: str | None) -> str:
    """
    统一把异步驱动切换为同步驱动：
      postgresql+asyncpg://...  → postgresql+psycopg://...
    迁移阶段必须走同步连接，避免 MissingGreenlet。
    """
    if not url:
        return ""
    # 优先把 +asyncpg 标记换掉
    if _ASYNCPG_RE.search(url):
        url = _ASYNCPG_RE.sub("+psycopg", url)
    return url


def _resolve_url() -> str:
    """
    解析数据库连接串优先级：
      1) 环境变量 DATABASE_URL
      2) alembic.ini -> sqlalchemy.url
    并做同步化处理。
    """
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DATABASE_URL or sqlalchemy.url configured for Alembic")
    return _sync_url(url)


def _include_object(
    obj: Any, name: str, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """
    Autogenerate 过滤策略：
      * 若对象仅存在于 DB（reflected=True）且模型元数据中不存在（compare_to is None），
        则跳过它，避免生成 DROP 语句。
    """
    if reflected and compare_to is None and type_ in {
        "table",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    }:
        return False
    return True


# ---- Offline / Online runners ------------------------------------------------
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
    """Run migrations in 'online' mode (同步引擎)."""
    url = _resolve_url()
    connectable = create_engine(url, poolclass=NullPool, future=True)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,  # 修正为标准参数名
            render_as_batch=False,        # SQLite 需要时再改 True
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
