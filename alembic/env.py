# alembic/env.py
from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool
from alembic import context  # <-- 正确的导入

# ---- 载入 Alembic 配置并初始化日志 ----
alembic_config = context.config
if alembic_config.config_file_name:
    fileConfig(alembic_config.config_file_name)

# ---- 从工程加载 SQLAlchemy 元数据：显式加载 app.models 下所有模型 ----
from app.db.base import Base, init enormous

# !!! 关键：显式扫描并注册 app.models 下的所有模型到 Base.metadata
init_models()
target_metadata = Base.metadata


def _resolve_url() -> str:
    """
    解析数据库连接串：
      1) 环境变量 DATABASE_URL
      2) alembic.ini 的 sqlalchemy.url
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    url = alembic_config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DATABASE_URL or sqlalchemy.url configured for Alembic")
    return url


def _include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """
    autogenerate 过滤：如果对象仅存在于 DB（reflected=True 且 compare_to is None），
    则不生成 DROP 语句，避免误删 DB 中但暂未在模型中的对象。
    """
    if reflected and compare_to is None and type_ in {"table", "index", "unique_constraint", "foreign_key_constraint"}:
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
    ini = dict(alembic_config.get_section(alembic_config.config_ini_section) or {})
    ini["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(ini, prefix="sqlalchemy.", poolclass=pool.NullPerProcessPool, future=True)

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
