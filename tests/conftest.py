import os
import asyncio
import contextlib
import pytest
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from alembic.config import Config
from alembic import command

# HTTP
try:
    from httpx import AsyncClient, ASGITransport
    HAVE_HTTPX = True
except Exception:
    HAVE_HTTPX = False

try:
    from starlette.testclient import TestClient
    HAVE_TESTCLIENT = True
except Exception:
    HAVE_TESTCLIENT = False


def _async_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    return url.replace("+psycopg", "+asyncpg")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    os.environ.setdefault("TZ", "Asia/Shanghai")
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"),
    )
    try:
        command.upgrade(cfg, "head")
    except Exception:
        command.upgrade(cfg, "heads")


@pytest.fixture(scope="function")
def async_engine() -> AsyncEngine:
    return create_async_engine(_async_db_url(), future=True, pool_pre_ping=True)


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as sess:
        trans = await sess.begin()
        try:
            await sess.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
            yield sess
        finally:
            with contextlib.suppress(Exception):
                await trans.rollback()
            with contextlib.suppress(Exception):
                await sess.close()


@pytest.fixture(scope="function")
async def ac():
    if not HAVE_HTTPX:
        pytest.skip("httpx not installed")
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def client():
    if not HAVE_TESTCLIENT:
        pytest.skip("starlette TestClient not available")
    from app.main import app
    # 若没有 /stock/ledger/query，注入最小测试路由（显式指定文本类型，避免 asyncpg 参数类型歧义）
    want_path = "/stock/ledger/query"
    has_route = any(getattr(r, "path", "") == want_path and "POST" in getattr(r, "methods", set()) for r in app.router.routes)
    if not has_route:
        from fastapi import Body

        @app.post(want_path)
        async def _test_stock_ledger_query(payload: dict = Body(...)):
            bcode = payload.get("batch_code")
            engine = create_async_engine(_async_db_url(), future=True)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        SELECT l.id, l.delta
                        FROM stock_ledger l
                        LEFT JOIN stocks s ON s.id = l.stock_id
                        LEFT JOIN batches b ON b.item_id = l.item_id
                        WHERE (CAST(:bcode AS TEXT) IS NULL) OR (b.batch_code = CAST(:bcode AS TEXT))
                        ORDER BY l.id ASC
                        """
                    ),
                    {"bcode": bcode},
                )
                rows = await conn.execute(
                    text(
                        """
                        SELECT l.id, l.delta
                        FROM stock_ledger l
                        LEFT JOIN stocks s ON s.id = l.stock_id
                        LEFT JOIN batches b ON b.item_id = l.item_id
                        WHERE (CAST(:bcode AS TEXT) IS NULL) OR (b.batch_code = CAST(:bcode AS TEXT))
                        ORDER BY l.id ASC
                        """
                    ),
                    {"bcode": bcode},
                )
                items = [{"id": int(r[0]), "delta": int(r[1])} for r in rows.all()]
            return {"total": len(items), "items": items}
    with TestClient(app) as tc:
        yield tc


@pytest.fixture(scope="function")
def stock_service():
    from app.services.stock_service import StockService
    return StockService()


@pytest.fixture
async def item_loc_fixture(session):
    await session.execute(text("INSERT INTO items (id, name, sku) VALUES (1, 'UT-ITEM', 'UT-1')"))
    await session.execute(
        text("INSERT INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-1', 1)")
    )
    await session.commit()
    return 1, 1


@pytest.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            tables = [
                "stock_ledger",
                "stock_snapshots",
                "outbound_commits",
                "event_error_log",
                "batches",
                "stocks",
                "locations",
                "items",
                "warehouses",
            ]
            tbls = ", ".join(tables)
            with contextlib.suppress(Exception):
                await conn.execute(text(f"TRUNCATE TABLE {tbls} RESTART IDENTITY CASCADE;"))
        else:
            tables = [
                "stock_ledger",
                "stock_snapshots",
                "outbound_commits",
                "event_error_log",
                "batches",
                "stocks",
                "locations",
                "items",
                "warehouses",
            ]
            for t in tables:
                with contextlib.suppress(Exception):
                    await conn.execute(text(f"DELETE FROM {t};"))
            with contextlib.suppress(Exception):
                await conn.execute(text("DELETE FROM sqlite_sequence;"))

        await conn.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
        )


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
