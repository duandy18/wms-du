# tests/conftest.py
import os
import re
import asyncio
import contextlib
import pytest
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Alembic programmatic API（在会话开始时把 DB 升到 head）
from alembic.config import Config
from alembic import command

# HTTP 测试（若你的用例依赖 HTTP 层）
try:
    from httpx import AsyncClient, ASGITransport
    HAVE_HTTPX = True
except Exception:
    HAVE_HTTPX = False


# ------------------------------
# 0) 统一解析数据库 URL（异步驱动）
# ------------------------------
def _async_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    return url.replace("+psycopg", "+asyncpg")


# ------------------------------
# 0.5) 标记并默认跳过“超出 v1.0 范围”的 legacy 用例
#     通过环境变量 RUN_Legacy=1 可恢复执行
# ------------------------------
LEGACY_PATTERNS = [
    r"tests/quick/test_new_platforms_pg\.py",
    r"tests/quick/test_platform_multi_shop_pg\.py",
    r"tests/quick/test_platform_outbound_commit_pg\.py",
    r"tests/quick/test_outbound_concurrency_pg\.py",
    r"tests/quick/test_platform_events_pg\.py",
    r"tests/quick/test_platform_state_machine_pg\.py",
    r"tests/smoke/test_platform_events_smoke_pg\.py",
]
LEGACY_REGEX = re.compile("|".join(LEGACY_PATTERNS))

def pytest_collection_modifyitems(config, items):
    run_legacy = os.getenv("RUN_LEGACY", "").lower() in {"1", "true", "yes", "on"}
    to_skip = []
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        if LEGACY_REGEX.search(nodeid):
            item.add_marker(pytest.mark.legacy)
            if not run_legacy:
                to_skip.append(item)
        else:
            item.add_marker(pytest.mark.phase1)
    if to_skip and not run_very_old := run_legacy:
        mark = pytest.mark.skip(reason="Skipping legacy (>v1.0) tests. Set RUN_LEGACY=1 to enable.")
        for it in to_skip:
            it.add_marker(mark)


# ------------------------------
# 1) 会话级：自动迁移到 head（如遇多头兜底到 heads）
# ------------------------------
@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"),
    )
    try:
        command.upgrade(cfg, "head")
    except Exception:
        # 极少数场景（历史遗留多 head），兜底到 heads，保证测试可跑
        command.upgrade(cfg, "heads")


# ------------------------------
# 2) 函数级：异步引擎/会话工厂
# ------------------------------
@pytest.fixture(scope="function")
def async_engine() -> AsyncEngine:
    """与每条用例的 event loop 生命周期一致"""
    return create_async_engine(_async_db_url(), future=True, pool_pre_ping=True)

@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """每条用例独立事务，结束回滚，保证隔离"""
    async with async_session_maker() as sess:
        trans = await sess.begin()
        try:
            yield sess
        finally:
            with contextlib.suppress(Exception):
                await trans.rollback()
            with contextlib.suppress(Exception):
                await sess.close()


# ------------------------------
# 3) HTTP 客户端（如需）
# ------------------------------
@pytest.fixture(scope="function")
async def ac():
    if not HAVE_HTTPX:
        pytest.skip("httpx not installed")
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(iline=transport, base_url="http://test") as client:
        yield client


# ------------------------------
# 4) 用例前清表 + 基线回种
# ------------------------------
@pytest.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    """
    清理顺序：先删子表再删父表，避免外键；最后回种 warehouses(id=1,'WH-1') 作为基线。
    """
    tables = [
        "stock_ledger",
        "stock_snapshots",
        "outbound_commits",
        "event_error_log",
        "stocks",
        "locations",
        "items",
        "warehouses",
    ]
    async with async_engine.begin() as conn:
        for t in tables:
            with contextlib.suppress(Exception):
                await conn.execute(text(f"DELETE FROM {t}"))
        await conn.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1, 'WH-1') ON CONFLICT (id) DO NOTHING")
        )


# ------------------------------
# 5) pytest-asyncio loop（会话级）
# ------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
