# tests/conftest.py
import os
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text


def _sync_url_from_env() -> str:
    """
    从环境变量 DATABASE_URL 生成 Alembic/同步 SQLAlchemy 可用的 URL。
    兼容以下写法：
      - postgresql+psycopg://...
      - postgresql+asyncpg://...
      - postgresql://...
    """
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5432/wms")
    # 测试中的 Alembic/DDL 走同步驱动：把 asyncpg 换回 psycopg
    url = url.replace("postgresql+asyncpg", "postgresql+psycopg")
    return url


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    测试会话启动时：
      1) 确保 alembic_version 存在 & version_num 扩到 255（幂等）
      2) 执行 alembic upgrade HEADS（兼容多 head 的迁移树）
    """
    sync_url = _sync_url_from_env()

    # 1) DDL：建表 + 扩列（幂等）
    eng = create_engine(sync_url, future=True)
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(255) PRIMARY KEY)"
            )
        )
        # 若列本来是 32，这里一次性扩容；如果已是 255，这条语句也安全
        conn.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
        )

    # 2) Alembic：升级到所有 head（不是 head）
    cfg = AlembicConfig("alembic.ini")
    # 某些 env.py 里读取 sqlalchemy.url，这里显式注入
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # 可选：打印当前/所有 heads（排查用，不影响执行）
    try:
        command.current(cfg)     # type: ignore[arg-type]
        command.heads(cfg, verbose=True)  # type: ignore[arg-type]
    except Exception:
        pass

    # 关键：兼容多分支迁移树
    command.upgrade(cfg, "heads")
