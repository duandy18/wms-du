# alembic/env.py
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 读取 alembic.ini 配置
config = context.config

# 日志配置（可选）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- 关键：引入项目 Base，并把 metadata 交给 Alembic ----
# 只需 import Base；各模型会由 app.db.base 内部集中导入注册
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# ---- 允许通过环境变量覆盖 sqlalchemy.url ----
# 优先取环境里的 DATABASE_URL（推荐形如 postgresql+psycopg://user:pass@host:port/db）
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# 也允许在 alembic.ini 里事先配置 sqlalchemy.url
sqlalchemy_url = config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Offline 模式：不连数据库，直接渲染 SQL。"""
    context.configure(
        url=sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 对比列类型差异（如 INTEGER → BIGINT / identity 等）
        compare_server_default=True,  # 对比 server_default 差异（如 now() / DEFAULT 0 等）
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online 模式：连接数据库并执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
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
            render_as_batch=False,  # 针对 SQLite 可设 True；PG 下保持 False 更安全
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
