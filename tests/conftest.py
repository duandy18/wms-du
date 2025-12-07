# tests/conftest.py
from __future__ import annotations

import os
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# ============================================================
# ★★ 关键：在 import app.main 之前强制设置 FULL_ROUTES ★★
# ============================================================
os.environ["FULL_ROUTES"] = "1"
os.environ["WMS_FULL_ROUTES"] = "1"

# FULL_ROUTES 设置完毕后再加载 FastAPI app
from app.main import app

# ==========================
# 数据库 DSN（强制 asyncpg）
# ==========================
DATABASE_URL = (
    os.getenv("WMS_TEST_DATABASE_URL")
    or os.getenv("WMS_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms"
)

# 规范化 DSN
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# =========================================
# 每用例独立 Engine（NullPool，避免跨 loop）
# =========================================
@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=False,
        future=True,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """
    标准 Session（自动 commit / rollback）
    """
    async with async_session_maker() as sess:
        await sess.execute(text("SET search_path TO public"))
        try:
            yield sess
            if sess.in_transaction():
                await sess.commit()
        except Exception:
            if sess.in_transaction():
                await sess.rollback()
            raise


# =========================================
# Soft Reserve 并发测试用长寿命 Session
# =========================================
@pytest_asyncio.fixture
async def db_session_like_pg(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as sess:
        await sess.execute(text("SET search_path TO public"))
        try:
            yield sess
        finally:
            if sess.in_transaction():
                await sess.rollback()


@pytest.fixture
def _maker(async_session_maker):
    """兼容历史测试：async with _maker() as sess"""
    return async_session_maker


# =========================================
# 清库 + 最小种子数据（每测试一次）
# =========================================
@pytest_asyncio.fixture(autouse=True, scope="function")
async def _db_clean_and_seed(async_engine: AsyncEngine):
    async with async_engine.begin() as conn:
        print("[TEST] 清理数据库并重建最小基线 ...")

        await conn.execute(
            text(
                """
            TRUNCATE TABLE
              order_items, orders,
              stock_ledger, stock_snapshots,
              outbound_commits, event_error_log,
              channel_inventory, store_items,
              stocks, batches, warehouses, items
            RESTART IDENTITY CASCADE
            """
            )
        )

        # 仓库
        await conn.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
        )

        # 商品
        await conn.execute(
            text(
                """
            INSERT INTO items (id,sku,name,qty_available)
            VALUES
              (1,'SKU-0001','UT-ITEM-1',0),
              (3001,'SKU-3001','SOFT-RESERVE-1',0),
              (3002,'SKU-3002','SOFT-RESERVE-2',0),
              (3003,'SKU-3003','SOFT-RESERVE-BASE',0),
              (4001,'SKU-4001','OUTBOUND-MERGE',0)
            ON CONFLICT (id) DO NOTHING
            """
            )
        )

        # 修正序列
        await conn.execute(
            text(
                """
            SELECT setval(
              pg_get_serial_sequence('warehouses','id'),
              COALESCE((SELECT MAX(id) FROM warehouses), 0),
              true
            )
            """
            )
        )
        await conn.execute(
            text(
                """
            SELECT setval(
              pg_get_serial_sequence('items','id'),
              COALESCE((SELECT MAX(id) FROM items), 0),
              true
            )
            """
            )
        )

        # 批次
        await conn.execute(
            text(
                """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES
              (1,1,'NEAR',CURRENT_DATE + INTERVAL '10 day'),
              (3001,1,'B-CONC-1',CURRENT_DATE + INTERVAL '7 day'),
              (3002,1,'B-OOO-1',CURRENT_DATE + INTERVAL '7 day'),
              (3003,1,'NEAR',CURRENT_DATE + INTERVAL '5 day'),
              (4001,1,'B-MERGE-1',CURRENT_DATE + INTERVAL '10 day')
            ON CONFLICT (item_id,warehouse_id,batch_code) DO NOTHING
            """
            )
        )

        # 库存
        await conn.execute(
            text(
                """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES
              (1,1,'NEAR',10),
              (3001,1,'B-CONC-1',3),
              (3002,1,'B-OOO-1',3),
              (3003,1,'NEAR',10),
              (4001,1,'B-MERGE-1',10)
            ON CONFLICT (item_id,warehouse_id,batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
            )
        )


# =========================================
# FastAPI / httpx AsyncClient
# =========================================
@pytest_asyncio.fixture(scope="function")
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=httpx.Timeout(10.0, connect=5.0, read=10.0, write=5.0, pool=5.0),
    ) as c:
        yield c


@pytest_asyncio.fixture
async def client_like(client: httpx.AsyncClient) -> AsyncGenerator[httpx.AsyncClient, None]:
    yield client
