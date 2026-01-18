# tests/conftest.py
from __future__ import annotations

import os
from pathlib import Path
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

# 测试专用：当测试用例不传 province 时，使用默认省份
# 仅在测试进程中生效，不影响生产
os.environ.setdefault("WMS_TEST_DEFAULT_PROVINCE", "UT")

from app.main import app  # noqa: E402
from scripts.seed_test_baseline import seed_in_conn  # noqa: E402

WMS_TEST_DATABASE_URL = os.getenv("WMS_TEST_DATABASE_URL")
WMS_DATABASE_URL = os.getenv("WMS_DATABASE_URL")
ALLOW_TRUNCATE = str(os.getenv("WMS_TEST_DB_ALLOW_TRUNCATE", "")).strip().lower() in {"1", "true", "yes"}

DATABASE_URL = WMS_TEST_DATABASE_URL or WMS_DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError(
        "WMS_TEST_DATABASE_URL / WMS_DATABASE_URL 未设置。\n"
        "建议显式指定测试库，例如：\n"
        "  export WMS_TEST_DATABASE_URL=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms_test\n"
    )

if not WMS_TEST_DATABASE_URL and not ALLOW_TRUNCATE:
    raise RuntimeError(
        "Refuse to TRUNCATE database because WMS_TEST_DATABASE_URL is not set.\n"
        "tests 会 TRUNCATE items/warehouses 并级联清空 item_barcodes。\n"
        "请设置独立测试库：WMS_TEST_DATABASE_URL=.../wms_test\n"
        "或（慎用）显式允许：WMS_TEST_DB_ALLOW_TRUNCATE=1"
    )

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


def _load_truncate_sql() -> str:
    base = Path(__file__).resolve().parent
    path = base / "fixtures" / "truncate.sql"
    if not path.exists():
        raise RuntimeError(f"truncate.sql not found: {path}")
    return path.read_text(encoding="utf-8")


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
    return async_session_maker


@pytest_asyncio.fixture(autouse=True, scope="function")
async def _db_clean_and_seed(async_engine: AsyncEngine):
    async with async_engine.begin() as conn:
        print("[TEST] TRUNCATE + seed baseline ...")
        await conn.execute(text("SET search_path TO public"))

        # 1) 清库（全部表清干净，避免脏数据累积）
        truncate_sql = _load_truncate_sql()
        await conn.execute(text(truncate_sql))

        # 2) 统一种子（items/barcodes/batches/stocks + shipping + admin + RBAC）
        old_dsn = os.environ.get("WMS_DATABASE_URL")
        os.environ["WMS_DATABASE_URL"] = DATABASE_URL
        try:
            await seed_in_conn(conn)
        finally:
            if old_dsn is None:
                os.environ.pop("WMS_DATABASE_URL", None)
            else:
                os.environ["WMS_DATABASE_URL"] = old_dsn

        # 3) Route C 测试基线：服务省份规则 + 店铺绑定（显式）
        # 3.1 取第一个仓库作为测试服务仓/默认绑定仓
        row = await conn.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
        wh_id = int(row.scalar_one())

        # 3.2 UT -> wh_id（幂等）
        await conn.execute(
            text(
                """
                INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
                VALUES (:wid, 'UT')
                ON CONFLICT (province_code) DO UPDATE
                  SET warehouse_id = EXCLUDED.warehouse_id
                """
            ),
            {"wid": wh_id},
        )

        # 3.3 确保至少存在一个 store（stores.name NOT NULL）
        row = await conn.execute(text("SELECT id FROM stores ORDER BY id ASC LIMIT 1"))
        any_store_id = row.scalar_one_or_none()
        if any_store_id is None:
            await conn.execute(
                text(
                    """
                    INSERT INTO stores(platform, shop_id, name, active)
                    VALUES('PDD', '1', 'UT-测试店铺', TRUE)
                    """
                )
            )

        # 3.4 将所有 stores 设为 active，并确保 name 非空（防御性）
        await conn.execute(
            text(
                """
                UPDATE stores
                   SET active = TRUE,
                       name = COALESCE(NULLIF(name, ''), platform || '-' || shop_id || '-测试店铺')
                """
            )
        )

        # 3.5 为所有 stores 绑定到 wh_id（幂等）
        rows = await conn.execute(text("SELECT id FROM stores"))
        store_ids = [int(x[0]) for x in rows.fetchall()]
        for sid in store_ids:
            await conn.execute(
                text(
                    """
                    INSERT INTO store_warehouse(store_id, warehouse_id, is_top, is_default, priority)
                    VALUES(:sid, :wid, TRUE, TRUE, 1)
                    ON CONFLICT (store_id, warehouse_id) DO UPDATE
                      SET is_top = EXCLUDED.is_top,
                          is_default = EXCLUDED.is_default,
                          priority = EXCLUDED.priority
                    """
                ),
                {"sid": sid, "wid": wh_id},
            )


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
