# tests/conftest.py
from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command


# ========================= 通用配置 =========================

def _async_db_url() -> str:
    """固定到 5433/wms 测试库，防止环境变量指向错误数据库。"""
    return "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms"


# ========================= 会话/引擎 =========================

@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """会话级自动迁移到 head；如遇多 head 兜底到 heads。"""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    try:
        command.upgrade(cfg, "head")
    except Exception:
        command.upgrade(cfg, "heads")


@pytest.fixture(scope="function")
def async_engine() -> AsyncEngine:
    """每条用例独立的异步引擎，固定连到 5433/wms。"""
    url = _async_db_url()
    print(f"[TEST] Using database: {url}")
    return create_async_engine(url, future=True, pool_pre_ping=True)


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """提供干净的 AsyncSession，不自动 begin/rollback。"""
    async with async_session_maker() as sess:
        yield sess


# ========================= 数据清理 & 基线回种 =========================

@pytest_asyncio.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    """逐表 TRUNCATE + RESTART IDENTITY + CASCADE。"""
    tables = [
        "stock_ledger",
        "stock_snapshots",
        "outbound_commits",
        "event_error_log",
        "batches",
        "stocks",
        "order_items",
        "orders",
        "channel_inventory",
        "store_items",
        "locations",
        "items",
        "stores",
        "warehouses",
        "platform_shops",
        "return_records",
    ]
    async with async_engine.begin() as conn:
        print("[TEST] Executing TRUNCATE on tables ...")
        for t in tables:
            with contextlib.suppress(Exception):
                await conn.execute(text(f"TRUNCATE {t} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _baseline_seed(_db_clean, async_engine: AsyncEngine):
    """基线回种（Lock-A 合法最小域）"""
    async with async_engine.begin() as conn:
        await conn.execute(text("INSERT INTO warehouses (id, name) VALUES (1, 'WH-1') ON CONFLICT (id) DO NOTHING"))
        await conn.execute(text("INSERT INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-1', 1) ON CONFLICT (id) DO NOTHING"))
        await conn.execute(text("INSERT INTO items (id, sku, name) VALUES (1, 'UT-ITEM-1', 'UT-ITEM') ON CONFLICT (id) DO NOTHING"))


# ========================= 事件循环 =========================

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
