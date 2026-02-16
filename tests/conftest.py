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

# Phase 5 Blueprint：禁止隐式省份兜底（必须显式提供 address.province）
os.environ.pop("WMS_TEST_DEFAULT_PROVINCE", None)

# ============================================================
# ★★ 关键：在 import app.main 之前强制把 DB env 绑定到测试库 ★★
# ============================================================
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

# ✅ 强制：API 侧（app.main -> app.db.session）也必须使用同一个测试库
os.environ["WMS_DATABASE_URL"] = DATABASE_URL
os.environ["WMS_TEST_DATABASE_URL"] = DATABASE_URL

# 重新读取（确保后续变量一致）
WMS_TEST_DATABASE_URL = os.getenv("WMS_TEST_DATABASE_URL")
WMS_DATABASE_URL = os.getenv("WMS_DATABASE_URL")

from app.main import app  # noqa: E402
from app.api.deps import get_session as app_get_session  # noqa: E402
from scripts.seed_test_baseline import seed_in_conn  # noqa: E402


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
        await seed_in_conn(conn)

        # 3) Route C 测试基线：服务省份规则 + 店铺绑定（显式）
        row = await conn.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
        wh_id = int(row.scalar_one())

        for prov in ("UT", "UT-P3", "UT-PROV"):
            await conn.execute(
                text(
                    """
                    INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
                    VALUES (:wid, :prov)
                    ON CONFLICT (province_code) DO UPDATE
                      SET warehouse_id = EXCLUDED.warehouse_id
                    """
                ),
                {"wid": wh_id, "prov": prov},
            )

        # ✅ Baseline 需要覆盖多条合同测试使用的 (platform, shop_id)
        # - PDD/1：历史 UT 默认
        # - DEMO/1：merchant-code-bindings / order ingest 等合同测试依赖
        await conn.execute(
            text(
                """
                INSERT INTO stores(platform, shop_id, name, active)
                VALUES ('PDD', '1', 'UT-测试店铺', TRUE)
                ON CONFLICT (platform, shop_id) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO stores(platform, shop_id, name, active)
                VALUES ('DEMO', '1', 'DEMO-1', TRUE)
                ON CONFLICT (platform, shop_id) DO NOTHING
                """
            )
        )

        await conn.execute(
            text(
                """
                UPDATE stores
                   SET active = TRUE,
                       name = COALESCE(NULLIF(name, ''), platform || '-' || shop_id || '-测试店铺')
                """
            )
        )

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
async def client(session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    关键：让同一个 test function 内的多次 HTTP 请求共享同一个 AsyncSession，
    以保证“写后读”在测试环境里可见（否则每个请求独立取连接，会出现 bind 后 ingest 看不到）。
    """

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[app_get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=httpx.Timeout(10.0, connect=5.0, read=10.0, write=5.0, pool=5.0),
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(app_get_session, None)


@pytest_asyncio.fixture
async def client_like(client: httpx.AsyncClient) -> AsyncGenerator[httpx.AsyncClient, None]:
    yield client
