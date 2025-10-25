# tests/conftest.py
import os
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
# 1) 会话级：自动迁移到 head（如遇多头兜底到 heads）
# ------------------------------
@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    # 统一系统时区到 Asia/Shanghai（UTC+8）
    os.environ.setdefault("TZ", "Asia/Shanghai")

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
# 2) 函数级异步引擎/会话工厂（避免不同 loop 冲突）
# ------------------------------
@pytest.fixture(scope="function")
def async_engine() -> AsyncEngine:
    """
    函数级 engine：与每条测试用例的 event loop 生命周期一致，
    杜绝 'Future attached to a different loop'。
    """
    return create_async_engine(_async_db_url(), future=True, pool_pre_ping=True)


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    """函数级会话工厂。部分用例会自己 new session 并 commit。"""
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """
    函数级事务会话：每条用例独立事务，结束时回滚，保证隔离。
    进入事务后，显式设置本地时区为 Asia/Shanghai（UTC+8）。
    """
    async with async_session_maker() as sess:
        trans = await sess.begin()
        try:
            # 关键：会话级事务里固定时区（不会影响其它连接）
            await sess.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
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
    """
    httpx.AsyncClient（ASGITransport）。
    若你的项目 app 入口路径不同，请把 import 改为实际路径。
    """
    if not HAVE_HTTPX:
        pytest.skip("httpx not installed")
    from app.main import app  # 若路径不同，改成你的应用入口
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ------------------------------
# 4) 每条用例开始前的“轻量清表 + 基线回种”
# ------------------------------
@pytest.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    """
    清理顺序：先删子表再删父表，避免外键；最后回种 warehouses(id=1,'WH-1') 基线。
    这样各 quick 用例中对 warehouse_id=1 的外键假设都能成立。
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
        # 基线维度回种（关键）：仓库表必须有 id=1，供 locations(..., warehouse_id=1) 外键引用
        await conn.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
        )


# ------------------------------
# 5) pytest-asyncio loop（会话级）
# ------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """为 pytest-asyncio 提供一个会话级 event loop。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
