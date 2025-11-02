# tests/conftest.py
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Tuple

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config

# ========================= 通用配置 =========================


def _async_db_url() -> str:
    """固定到 5433/wms 测试库，防止环境变量指向错误数据库。"""
    return "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms"


# ========================= 会话/引擎 =========================


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """
    会话级自动迁移到 head；如遇多 head 兜底到 heads。
    迁移阶段必须使用同步驱动（psycopg），避免 MissingGreenlet。
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    try:
        command.upgrade(cfg, "head")
    except Exception:
        command.upgrade(cfg, "heads")


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    每条用例独立的异步引擎；yield 后优雅回收连接池。
    """
    url = _async_db_url()
    print(f"[TEST] Using database: {url}")
    engine = create_async_engine(url, future=True, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """提供干净的 AsyncSession，不自动 begin/rollback。"""
    async with async_session_maker() as sess:
        yield sess


# ========================= 覆盖 FastAPI 依赖 =========================
# 关键：让路由里的 get_session 与测试用例使用同一个 AsyncSession

from app.api import deps as api_deps  # noqa: E402


@pytest.fixture(autouse=True)
def _override_dep_session(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """
    将 FastAPI 依赖 app.api.deps.get_session 覆盖为返回当前测试的 session。
    保证 /scan 路由与测试回查共用同一会话/同一 search_path/同一事务边界。
    """
    async def _yield_test_session():
        yield session

    monkeypatch.setattr(api_deps, "get_session", _yield_test_session)


# ========================= 数据清理 & 基线回种 =========================


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    """
    一次性强力清库：
      - TRUNCATE 多表（单条语句）；
      - RESTART IDENTITY 重置自增；
      - CASCADE 级联外键，避免顺序问题。
    """
    async with async_engine.begin() as conn:
        print("[TEST] Executing TRUNCATE on tables ...")
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
                  batches,
                  stocks
                RESTART IDENTITY CASCADE
                """
            )
        )


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _baseline_seed(_db_clean, async_engine: AsyncEngine):
    """
    基线回种（Lock-A 合法最小域）。
    注意：locations 现已规范化，必须显式提供 code（与 name 等值亦可）。
    """
    async with async_engine.begin() as conn:
        # ---- 基础仓 ----
        await conn.execute(
            text(
                "INSERT INTO warehouses (id, name) VALUES (1, 'WH-1') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )

        # ---- 标准库位（显式 code）----
        # 兼容旧测试：保留 id=1 的最小位；name 与 code 同值
        await conn.execute(
            text(
                "INSERT INTO locations (id, name, code, warehouse_id) "
                "VALUES (1, 'LOC-1', 'LOC-1', 1) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )

        # 可选：提供两个系统位（接收入库位 / 暂存位），便于扫码通路专项用例复用
        await conn.execute(
            text(
                "INSERT INTO locations (name, code, warehouse_id) VALUES "
                "('01R0000000','01R0000000',1), "
                "('01S9000000','01S9000000',1) "
                "ON CONFLICT (warehouse_id, code) DO NOTHING"
            )
        )

        # ---- 最小商品 ----
        await conn.execute(
            text(
                "INSERT INTO items (id, sku, name, shelf_life_days) "
                "VALUES (1, 'UT-ITEM-1', 'UT-ITEM', 0) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )

        # （如有需要，可在各自用例中插入条码映射/更复杂主数据）
        # 这里保持基线最小化，避免对特定业务通路产生隐式耦合。


# ========================= A组所需 Fixtures =========================

from app.services.stock_service import StockService  # noqa: E402


@pytest_asyncio.fixture
async def stock_service() -> StockService:
    """A 组测试使用的 StockService 简易装配。"""
    return StockService()


@pytest_asyncio.fixture
async def item_loc_fixture() -> Tuple[int, int]:
    """A组测试的起跑线：固定 (item_id=1, location_id=1)。"""
    return (1, 1)


# ========================= 事件循环 =========================


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
