# tests/conftest.py
import os
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text

def _sync_url_from_env() -> str:
    """
    把环境变量里的 DATABASE_URL 规范成 Alembic 可用的“同步”URL。
    兼容以下几种写法：
      - postgresql+psycopg://...
      - postgresql+asyncpg://...
      - postgresql://...
    """
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5432/wms")
    # alembic/SQLAlchemy 同步驱动优先用 psycopg; 如果传进来是 asyncpg，则换回 psycopg
    url = url.replace("postgresql+asyncpg", "postgresql+psycopg")
    # 亦容忍直接写 postgresql://
    return url

@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    测试会话启动时：
      1) 幂等保障 alembic_version 存在、version_num 扩到 255
      2) 执行 alembic upgrade heads（兼容多 head）
    """
    sync_url = _sync_url_from_env()

    # 1) DDL: 建表 + 扩列，幂等
    eng = create_engine(sync_url, future=True)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(255) PRIMARY KEY)"
        ))
        conn.execute(text(
            "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
        ))

    # 2) Alembic 升级到所有 heads
    cfg = AlembicConfig("alembic.ini")
    # 有些 env.py 依赖 sqlalchemy.url，需要显式注入
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # 打印当前heads（非必要，仅排查时有用）
    try:
        command.heads(cfg, verbose=True)  # type: ignore[arg-type]
    except Exception:
        pass

    # 关键：升级到所有 head（不是 head）
    command.upgrade(cfg, "heads")
