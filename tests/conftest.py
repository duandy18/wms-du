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
