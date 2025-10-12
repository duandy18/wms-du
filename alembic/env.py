# alembic/env.py
# 方案：不依赖项目 Base；用 DATABASE_URL 执行迁移；
#       预建 255 长度的 alembic_version，并禁止 Alembic 自建 32 长度版本表。

import os
import re
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context

# ---------- 基本配置 ----------
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 不导入项目 Base，避免副作用（自动比较/自发现由迁移脚本负责）
target_metadata = None


# ---------- DSN 归一（把 async → sync，便于 Alembic 直连） ----------
def _normalize_sync_dsn(url: str) -> str:
    if not url:
        return url
    # postgres / postgresql / postgresql+asyncpg → postgresql+psycopg
    if url.startswith("postgresql+asyncpg://") or url.startswith("postgres+asyncpg://"):
        return re.sub(r"^postgres(?:ql)?\+asyncpg://", "postgresql+psycopg://", url)
    if url.startswith("postgres://"):
        return re.sub(r"^postgres://", "postgresql+psycopg://", url)
    if url.startswith("postgresql://"):
        return re.sub(r"^postgresql://", "postgresql+psycopg://", url)
    # SQLite 保持原样；其他驱动按原样返回
    return url


def get_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "❌ DATABASE_URL 未设置。例如：\n"
            "export DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:5432/wms'\n"
            "或：export DATABASE_URL='sqlite:///dev.db'"
        )
    return _normalize_sync_dsn(url)


# ---------- 版本表（255）预建 ----------
def _ensure_version_table_255(conn: sa.engine.Connection) -> None:
    """
    统一确保存在 `alembic_version(version_num VARCHAR(255))`，
    并禁止 Alembic 自己创建 32 长度版本表。
    """
    dialect = conn.dialect.name

    if dialect == "postgresql":
        # PostgreSQL：IF NOT EXISTS 写法最简洁（>=9.5）
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(255) NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS alembic_version_pkc
                ON alembic_version (version_num);
            """
        )
    elif dialect == "sqlite":
        # SQLite：TEXT 等价；保持唯一性
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS alembic_version_pkc
                ON alembic_version (version_num);
            """
        )
    else:
        # 其它方言：尽量使用通用 SQL
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(255) NOT NULL
            )
            """
        )
        try:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS alembic_version_pkc ON alembic_version (version_num)"
            )
        except Exception:
            # 某些方言/版本不支持 IF NOT EXISTS 索引，容错
            pass


# ---------- Offline 模式 ----------
def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
        version_table="alembic_version",
        version_table_column="version_num",
        create_version_table=False,  # 关键：由我们预建 255
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------- Online 模式 ----------
def run_migrations_online() -> None:
    url = get_url()
    engine = sa.create_engine(url, pool_pre_ping=True, future=True)

    with engine.connect() as connection:
        # 预建版本表（255），避免 Alembic 创建 32 长度
        _ensure_version_table_255(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
            version_table="alembic_version",
            version_table_column="version_num",
            create_version_table=False,  # 禁止 Alembic 自建
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
