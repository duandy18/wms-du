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
    # 测试侧 Alembic/DDL 用同步驱动：把 asyncpg 换回 psycopg
    return url.replace("postgresql+asyncpg", "postgresql+psycopg")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    测试会话启动时：
      - 若 CI 已做迁移（CI_SKIP_TEST_MIGRATE=1），则跳过测试内迁移；
      - 否则：幂等保障 alembic_version 存在、version_num 扩到 255 → alembic upgrade HEADS。
    """
    if os.getenv("CI_SKIP_TEST_MIGRATE") == "1":
        # CI 的 workflow 已完成建表/扩列 + upgrade heads，这里不重复做
        yield
        return

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
        conn.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
        )

    # 2) Alembic：升级到所有 head（不是 head），兼容多分支迁移树
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # 可选：打印当前/所有 heads（辅助排障，不影响执行）
    try:
        command.current(cfg)                 # type: ignore[arg-type]
        command.heads(cfg, verbose=True)     # type: ignore[arg-type]
    except Exception:
        pass

    command.upgrade(cfg, "heads")
    yield
