# tests/conftest.py
# -*- coding: utf-8 -*-
"""
测试基座（Smoke→Full 两段式友好）：
- 会话期：Alembic 升级到 head（若存在迁移），并按当前 DATABASE_URL 初始化连接
- 用例级：轻量清表 + 预置最小维度；每例结束回滚，保持极快
- 双模：PostgreSQL / SQLite 自动适配（异步 DSN 统一为 asyncpg/aiosqlite）
- 覆盖 FastAPI 依赖（get_session / get_db），保证 API/Service 测试走同一会话
"""
import asyncio
import os
import re
from contextlib import contextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.main import app

# ---------------- DSN 归一 ----------------

def _normalize_async_dsn(url: str) -> str:
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite://" + url[len("sqlite:///") - 1 :]
    return re.sub(r"^postgresql\+?[^:]*://", "postgresql+asyncpg://", url)

def _is_pg(url: str) -> bool:
    return url.startswith("postgresql")

def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")

RAW_URL = os.getenv("DATABASE_URL_TEST") or os.getenv("DATABASE_URL") or "sqlite:///test.db"
ASYNC_URL = _normalize_async_dsn(RAW_URL)
IS_PG = _is_pg(RAW_URL)
IS_SQLITE = _is_sqlite(RAW_URL)
ALEMBIC_SYNC_URL = (
    RAW_URL.replace("+asyncpg", "+psycopg") if RAW_URL.startswith("postgresql+asyncpg") else RAW_URL
)

# ---------------- 事件循环 ----------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ---------------- 导入模型 ----------------

def _import_all_models():
    from app.models.batch import Batch  # noqa
    from app.models.item import Item  # noqa
    from app.models.location import Location  # noqa
    from app.models.stock import Stock  # noqa
    from app.models.stock_ledger import StockLedger  # noqa
    from app.models.warehouse import Warehouse  # noqa
    try:
        from app.models.stock_snapshot import StockSnapshot  # noqa
    except Exception:
        pass
    try:
        from app.models.order import Order, OrderItem  # noqa
    except Exception:
        pass

# ---------------- 会话级：Alembic 升级（PG: smart stamp；SQLite: create_all 兜底） ----------------

@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    - 若存在 alembic.ini（或迁移目录），执行升级
    - **Smart stamp（仅 PG）**：若库里已有核心表但没有 alembic_version，先 stamp 到 baseline 再升级
    - 仅在 **SQLite** 场景使用 Base.metadata.create_all() 兜底
    """
    _import_all_models()

    need_alembic = os.path.exists("alembic.ini") or os.path.isdir("alembic")
    if need_alembic:
        from alembic import command
        from alembic.config import Config

        prev = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = ALEMBIC_SYNC_URL
        try:
            cfg = Config("alembic.ini")
            cfg.set_main_option("sqlalchemy.url", ALEMBIC_SYNC_URL)

            if IS_PG:
                sync_eng = create_engine(ALEMBIC_SYNC_URL, future=True, pool_pre_ping=True)
                try:
                    insp = inspect(sync_eng)
                    has_version = insp.has_table("alembic_version")
                    existing = set(insp.get_table_names())
                    core_tables = {"items", "warehouses", "locations"}
                    has_core = bool(core_tables & existing)
                    if (not has_version) and has_core:
                        command.stamp(cfg, "f995a82ac74e")
                finally:
                    sync_eng.dispose()

            command.upgrade(cfg, "head")
        finally:
            if prev is not None:
                os.environ["DATABASE_URL"] = prev
            else:
                os.environ.pop("DATABASE_URL", None)

    if ALEMBIC_SYNC_URL.startswith("sqlite"):
        sync_eng = create_engine(
            ALEMBIC_SYNC_URL,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 60},
        )
        try:
            Base.metadata.create_all(sync_eng)
        finally:
            sync_eng.dispose()

# ---------------- 同步 Engine / Session ----------------

def _make_sync_engine():
    if IS_PG:
        eng = create_engine(ALEMBIC_SYNC_URL, future=True, pool_pre_ping=True)
    else:
        eng = create_engine(
            RAW_URL,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 60} if IS_SQLITE else {},
            pool_pre_ping=True,
        )
    return eng

SyncSessionLocal = sessionmaker(bind=_make_sync_engine(), class_=Session, expire_on_commit=False)

@contextmanager
def sync_conn():
    eng = _make_sync_engine()
    try:
        with eng.begin() as conn:
            yield conn
    finally:
        eng.dispose()

# ---------------- PG：确保最小三表且补缺列（幂等） ----------------

def _ensure_core_tables_pg(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id   INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE
        );
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS locations (
            id           INTEGER PRIMARY KEY,
            name         VARCHAR(100) NOT NULL,
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
            CONSTRAINT uq_locations_wh_name UNIQUE (warehouse_id, name)
        );
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS items (
            id            INTEGER PRIMARY KEY,
            sku           VARCHAR(64)  NOT NULL UNIQUE,
            name          VARCHAR(200) NOT NULL,
            unit          VARCHAR(16)  NOT NULL DEFAULT 'EA',
            qty_available INTEGER      NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
    """))
    conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS qty_available INTEGER NOT NULL DEFAULT 0;"))
    conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();"))
    conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();"))

# ---------------- 用例级：清表 + 种子 ----------------

@pytest.fixture(autouse=True)
def _fresh_db():
    _import_all_models()

    if IS_PG:
        with sync_conn() as conn:
            _ensure_core_tables_pg(conn)

            rows = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).fetchall()
            existing = {r[0] for r in rows}
            target = [
                "stock_snapshots",
                "stock_ledger",
                "stocks",
                "batches",
                "order_items",
                "orders",
                "items",
                "locations",
                "warehouses",
            ]
            present = [t for t in target if t in existing]
            if present:
                conn.execute(
                    text("TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in present) + " RESTART IDENTITY CASCADE")
                )

        from app.models.item import Item
        from app.models.location import Location
        from app.models.warehouse import Warehouse

        s = SyncSessionLocal()
        try:
            if s.query(Warehouse).filter_by(id=1).first() is None:
                s.add(Warehouse(id=1, name="WH-TEST"))
            if s.query(Location).filter_by(id=1).first() is None:
                s.add(Location(id=1, name="LOC-TEST", warehouse_id=1))
            itm = s.query(Item).filter_by(id=1).first()
            if itm is None:
                itm = Item(id=1, sku="SKU-TEST-1", name="测试商品-1")
                for fld in ("qty_available", "qty_on_hand", "qty_reserved", "qty", "min_qty", "max_qty"):
                    if hasattr(Item, fld) and getattr(itm, fld, None) is None:
                        setattr(itm, fld, 0)
                if hasattr(Item, "unit") and getattr(itm, "unit", None) is None:
                    itm.unit = "EA"
                s.add(itm)
            s.commit()
        finally:
            s.close()
    else:
        eng = _make_sync_engine()
        Base.metadata.create_all(eng)
        with eng.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF;")
            for tbl in [
                "stock_snapshots",
                "stock_ledger",
                "stocks",
                "batches",
                "order_items",
                "orders",
                "items",
                "locations",
                "warehouses",
            ]:
                try:
                    conn.exec_driver_sql(f"DELETE FROM {tbl};")
                except Exception:
                    pass
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
            conn.exec_driver_sql("INSERT OR IGNORE INTO warehouses (id, name) VALUES (1, 'WH-TEST');")
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-TEST', 1);"
            )
        eng.dispose()

    yield

# ---------------- 异步 Engine / Session ----------------

@pytest.fixture(scope="session")
def db_url():
    return ASYNC_URL

@pytest.fixture(scope="session")
async def engine(db_url):
    # 重要修复：PG + psycopg3 不能使用 connect_args['server_settings']，改为空 dict
    connect_args = {} if IS_PG else {"timeout": 10}
    eng = create_async_engine(
        db_url,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=connect_args,
        echo=False,
    )
    try:
        yield eng
    finally:
        await eng.dispose()

@pytest_asyncio.fixture()
async def session(engine):
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        tx = await s.begin()
        try:
            yield s
        finally:
            await tx.rollback()

# ---------------- FastAPI 依赖覆盖 ----------------

@pytest.fixture(autouse=True)
def _override_fastapi_deps():
    try:
        from app.db.session import get_session as _get_async_dep
    except Exception:
        _get_async_dep = None
    try:
        from app.db.session import get_async_session as _get_async_dep_alt
    except Exception:
        _get_async_dep_alt = None
    try:
        from app.db.session import get_db as _get_sync_dep
    except Exception:
        _get_sync_dep = None

    async def _get_async_override():
        # 同样修复：PG 下 connect_args 置空
        connect_args = {} if IS_PG else {"timeout": 10}
        maker = async_sessionmaker(
            bind=create_async_engine(ASYNC_URL, future=True, pool_pre_ping=True, poolclass=NullPool, connect_args=connect_args),
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            async with maker() as s:
                yield s
        finally:
            await s.close()
            await s.bind.dispose()  # type: ignore[attr-defined]

    def _get_sync_override():
        s = SyncSessionLocal()
        try:
            yield s
        finally:
            s.close()

    if _get_async_dep is not None:
        app.dependency_overrides[_get_async_dep] = _get_async_override
    if _get_async_dep_alt is not None:
        app.dependency_overrides[_get_async_dep_alt] = _get_async_override
    if _get_sync_dep is not None:
        app.dependency_overrides[_get_sync_dep] = _get_sync_override

    try:
        yield
    finally:
        if _get_async_dep is not None:
            app.dependency_overrides.pop(_get_async_dep, None)
        if _get_async_dep_alt is not None:
            app.dependency_overrides.pop(_get_async_dep_alt, None)
        if _get_sync_dep is not None:
            app.dependency_overrides.pop(_get_sync_dep, None)

# ---------------- HTTP 客户端 ----------------

@pytest.fixture()
async def ac():
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    try:
        yield client
    finally:
        await client.aclose()

@pytest.fixture()
def tc():
    c = TestClient(app)
    try:
        yield c
    finally:
        c.close()

# ---------------- 最小维度种子 ----------------

@pytest.fixture()
def item_loc_fixture():
    """返回 (item_id, location_id)"""
    from app.models.item import Item
    from app.models.location import Location
    from app.models.warehouse import Warehouse

    s = SyncSessionLocal()
    try:
        wh = s.query(Warehouse).filter_by(id=1).first()
        if not wh:
            wh = Warehouse(id=1, name="WH-TEST")
            s.add(wh)
            s.flush()

        loc = s.query(Location).filter_by(id=1).first()
        if not loc:
            loc = Location(id=1, name="LOC-TEST", warehouse_id=wh.id)
            s.add(loc)
            s.flush()

        item = s.query(Item).filter_by(sku="SKU-TEST").first()
        if not item:
            item = Item(sku="SKU-TEST", name="测试商品")
            for fld in ("qty_available", "qty_on_hand", "qty_reserved", "qty", "min_qty", "max_qty"):
                if hasattr(Item, fld) and getattr(item, fld, None) is None:
                    setattr(item, fld, 0)
            if hasattr(Item, "unit") and getattr(item, "unit", None) is None:
                item.unit = "EA"
            s.add(item)
            s.flush()

        s.commit()
        return (item.id, loc.id)
    finally:
        s.close()

# ---------------- StockService 异步适配 ----------------

class StockServiceAsyncAdapter:
    def __init__(self, svc):
        self._svc = svc

    async def adjust(self, **kwargs):
        session = kwargs.pop("session")
        return await self._svc.adjust(session=session, **kwargs)

@pytest.fixture()
def stock_service():
    try:
        from app.services.stock_service import StockService
    except Exception:
        pytest.skip("StockService not available")
    return StockServiceAsyncAdapter(StockService(SyncSessionLocal()))

# ---------------- Pytest markers ----------------

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: ultra-fast path tests (inbound core, barcode 400, expiry 422, negative stock, idempotency)")
    config.addinivalue_line("markers", "pg: tests requiring PostgreSQL-specific behavior")
    config.addinivalue_line("markers", "sqlite: tests requiring SQLite behavior")
    config.addinivalue_line("markers", "asyncio: mark test as running with asyncio")
