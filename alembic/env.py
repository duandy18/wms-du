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


def _resolve_sqlalchemy_url() -> str:
    """
    统一解析数据库 URL：
    1) 优先环境变量 DATABASE_URL
    2) 其次 alembic.ini 中的 sqlalchemy.url
    3) 都没有则给出清晰报错
    """
    env_url = (os.getenv("DATABASE_URL") or "").strip()
    if env_url:
        return env_url

    ini_url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if ini_url:
        return ini_url

    raise RuntimeError(
        "Alembic: missing DB URL.\n"
        "请设置环境变量 DATABASE_URL（例如：postgresql+psycopg://wms:wms@127.0.0.1:5433/wms），"  # pragma: allowlist secret
        "或在 alembic.ini 的 [alembic] 区块中配置 sqlalchemy.url。"
    )


def run_migrations_offline() -> None:
    """Offline 模式：不连数据库，直接渲染 SQL。"""
    url = _resolve_sqlalchemy_url()
    context.configure(
        url=url,
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
    url = _resolve_sqlalchemy_url()

    # 确保传给 engine_from_config 的 dict 内含 'sqlalchemy.url'
    section = config.get_section(config.config_ini_section) or {}
    section = dict(section)  # 复制，避免影响全局 config
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration=section,
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
