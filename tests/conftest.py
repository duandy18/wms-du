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
from app.main import app  # noqa: E402

# ==========================
# 数据库 DSN（强制显式配置，禁止自适应 fallback）
# ==========================

DATABASE_URL = os.getenv("WMS_TEST_DATABASE_URL") or os.getenv("WMS_DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "WMS_TEST_DATABASE_URL / WMS_DATABASE_URL 未设置。\n"
        "请显式指定，例如：\n"
        "  export WMS_TEST_DATABASE_URL=postgresql+psycopg://postgres:wms@127.0.0.1:55432/postgres"
    )

# 规范化 DSN：兼容老式 postgres:// / postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


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
async def db_session_like_pg(
    async_session_maker,
) -> AsyncGenerator[AsyncSession, None]:
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
#   ★ 不再根据 schema 自适应，有问题直接炸，暴露迁移问题
# =========================================
@pytest_asyncio.fixture(autouse=True, scope="function")
async def _db_clean_and_seed(async_engine: AsyncEngine):
    async with async_engine.begin() as conn:
        print("[TEST] 清理数据库并重建最小基线 ...")

        # 这里假定数据库已经按 HEAD schema 完整迁移，
        # 有 warehouses/items/batches/stocks/reservations 等表。
        await conn.execute(
            text(
                """
            TRUNCATE TABLE
              order_items,
              orders,
              stock_ledger,
              stock_snapshots,
              outbound_commits,
              event_error_log,
              channel_inventory,
              store_items,
              reservation_allocations,
              reservation_lines,
              reservations,
              stocks,
              batches,
              warehouses,
              items
            RESTART IDENTITY CASCADE
            """
            )
        )

        # 仓库（HEAD schema 下 warehouses 至少有 id/name）
        await conn.execute(
            text(
                "INSERT INTO warehouses (id, name) "
                "VALUES (1,'WH-1')"
            )
        )

        # 商品（用当前 HEAD 里的 items 结构：有 qty_available）
        await conn.execute(
            text(
                """
            INSERT INTO items (id, sku, name, qty_available)
            VALUES
              (1,    'SKU-0001','UT-ITEM-1',           0),
              (3001, 'SKU-3001','SOFT-RESERVE-1',      0),
              (3002, 'SKU-3002','SOFT-RESERVE-2',      0),
              (3003, 'SKU-3003','SOFT-RESERVE-BASE',   0),
              (4001, 'SKU-4001','OUTBOUND-MERGE',      0)
            """
            )
        )

        # 修正序列（以 HEAD schema 为准，有 serial/identity 时生效）
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

        # 批次：按最终世界观写，有 warehouse_id / item_id / batch_code / expiry_date
        await conn.execute(
            text(
                """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES
              (1,    1,'NEAR',      CURRENT_DATE + INTERVAL '10 day'),
              (3001, 1,'B-CONC-1',  CURRENT_DATE + INTERVAL '7 day'),
              (3002, 1,'B-OOO-1',   CURRENT_DATE + INTERVAL '7 day'),
              (3003, 1,'NEAR',      CURRENT_DATE + INTERVAL '5 day'),
              (4001, 1,'B-MERGE-1', CURRENT_DATE + INTERVAL '10 day')
            """
            )
        )

        # 库存：按最终世界观写，有 warehouse_id / item_id / batch_code / qty
        await conn.execute(
            text(
                """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES
              (1,    1,'NEAR',      10),
              (3001, 1,'B-CONC-1',   3),
              (3002, 1,'B-OOO-1',    3),
              (3003, 1,'NEAR',      10),
              (4001, 1,'B-MERGE-1', 10)
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
async def client_like(
    client: httpx.AsyncClient,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    yield client
