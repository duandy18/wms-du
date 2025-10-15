# tests/conftest.py
import asyncio
import contextlib
import os
import re
from contextlib import contextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.main import app


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


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _import_all_models():
    for imp in (
        "app.models.item",
        "app.models.warehouse",
        "app.models.location",
        "app.models.stock",
        "app.models.stock_ledger",
        "app.models.stock_snapshot",
        "app.models.batch",
        "app.models.order",
    ):
        try:
            __import__(imp)
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
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
                    if (not has_version) and {"items", "warehouses", "locations"} & existing:
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
            ALEMBIC_SYNC_URL, future=True, connect_args={"check_same_thread": False, "timeout": 60}
        )
        try:
            Base.metadata.create_all(sync_eng)
        finally:
            sync_eng.dispose()


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


def _ensure_core_tables_pg(conn):
    # warehouses
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS warehouses (
            id   INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE
        );
    """
        )
    )
    # locations —— 不再创建 (warehouse_id, name) 唯一约束
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS locations (
            id           INTEGER PRIMARY KEY,
            name         VARCHAR(100) NOT NULL,
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT
        );
    """
        )
    )
    # 兼容旧库：幂等删除历史唯一约束
    conn.execute(
        text(
            """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_locations_wh_name'
              AND conrelid = 'public.locations'::regclass
          ) THEN
            ALTER TABLE public.locations DROP CONSTRAINT uq_locations_wh_name;
          END IF;
        END$$;
    """
        )
    )
    # items
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS items (
            id            INTEGER PRIMARY KEY,
            sku           VARCHAR(64)  NOT NULL UNIQUE,
            name          VARCHAR(200) NOT NULL,
            unit          VARCHAR(16)  NOT NULL DEFAULT 'EA',
            qty_available INTEGER      NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
    """
        )
    )
    conn.execute(
        text("ALTER TABLE items ADD COLUMN IF NOT EXISTS qty_available INTEGER NOT NULL DEFAULT 0;")
    )
    conn.execute(
        text(
            "ALTER TABLE items ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();"
        )
    )


def _reseed_items_seq_pg(conn):
    conn.execute(
        text(
            """
        SELECT setval(
          COALESCE(pg_get_serial_sequence('public.items','id'), pg_get_serial_sequence('items','id')),
          COALESCE( (SELECT MAX(id) FROM public.items), 0 ),
          true
        );
    """
        )
    )


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
                    text(
                        "TRUNCATE TABLE "
                        + ", ".join(f'"{t}"' for t in present)
                        + " RESTART IDENTITY CASCADE"
                    )
                )

        # 最小种子：WH=1、LOC=0/101、ITEM#1=SKU-001（与 smoke 断言一致）
        s = SyncSessionLocal()
        try:
            s.execute(
                text(
                    "INSERT INTO warehouses (id, name) VALUES (1,'WH-TEST') ON CONFLICT (id) DO NOTHING"
                )
            )
            s.execute(
                text(
                    "INSERT INTO locations (id, name, warehouse_id) VALUES (0,'STAGE',1) ON CONFLICT (id) DO NOTHING"
                )
            )
            s.execute(
                text(
                    "INSERT INTO locations (id, name, warehouse_id) VALUES (101,'LOC-101',1) ON CONFLICT (id) DO NOTHING"
                )
            )
            s.execute(
                text(
                    "INSERT INTO items (id, sku, name, unit) VALUES (1,'SKU-001','Item-1','EA') ON CONFLICT (id) DO NOTHING"
                )
            )
            s.commit()
        finally:
            s.close()

        with sync_conn() as conn:
            _reseed_items_seq_pg(conn)
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
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO warehouses (id, name) VALUES (1,'WH-TEST');"
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO locations (id, name, warehouse_id) VALUES (0,'STAGE',1);"
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO locations (id, name, warehouse_id) VALUES (101,'LOC-101',1);"
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO items (id, sku, name, unit) VALUES (1,'SKU-001','Item-1','EA');"
            )
        eng.dispose()
    yield


@pytest.fixture(scope="session")
def db_url():
    return ASYNC_URL


@pytest_asyncio.fixture(scope="session")
async def engine(db_url):
    connect_args = {} if IS_PG else {"timeout": 10}
    eng = create_async_engine(
        db_url, future=True, pool_pre_ping=True, poolclass=NullPool, connect_args=connect_args
    )
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture()
async def async_session_maker(engine):
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture()
async def session(async_session_maker):
    async with async_session_maker() as s:
        tx = await s.begin()
        try:
            yield s
        finally:
            with contextlib.suppress(Exception):
                if tx.is_active:
                    await tx.rollback()
                else:
                    await s.rollback()


# === 关键：让 /inbound/* 与断言共享同一会话/Engine ===
import pytest as _pytest

from app.api.endpoints import inbound as _inbound


@_pytest.fixture(autouse=True)
def _override_inbound_session(async_session_maker):
    async def _get_async_override():
        async with async_session_maker() as s:
            yield s

    app.dependency_overrides[_inbound.get_session] = _get_async_override
    try:
        yield
    finally:
        app.dependency_overrides.pop(_inbound.get_session, None)


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
