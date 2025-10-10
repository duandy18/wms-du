# alembic/env.py  —— 方案 B：预建 255 长度版本表 + 不依赖 Base

import os
from logging.config import fileConfig

import sqlalchemy as sa

from alembic import context

# 让 alembic.ini 的日志配置生效
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 这里不用 Base，避免导入项目代码
target_metadata = None


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "❌ DATABASE_URL 未设置。请先导出，例如：\n"
            "export DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:55432/wms_du'"
        )
    return url


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 而不连库。"""
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
        create_version_table=False,  # 重要：我们手动预建
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移。"""
    url = get_url()
    engine = sa.create_engine(url, pool_pre_ping=True, future=True)

    with engine.connect() as connection:
        # —— 预建 alembic_version（255），如果不存在就创建 —— #
        # 注意：PostgreSQL 语法；SQLite 也能跑，但这里我们现在是 PG。
        connection.exec_driver_sql(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'alembic_version' AND c.relkind = 'r'
                ) THEN
                    CREATE TABLE alembic_version (
                        version_num VARCHAR(255) NOT NULL
                    );
                    CREATE UNIQUE INDEX alembic_version_pkc ON alembic_version (version_num);
                END IF;
            END$$;
            """
        )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
            version_table="alembic_version",
            version_table_column="version_num",
            create_version_table=False,  # 关键：禁止 Alembic 自建 32 长度表
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
