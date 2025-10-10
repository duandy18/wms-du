# tests/conftest.py
import asyncio
import os

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.main import app


# ============== 会话级事件循环 ==============
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============== 数据库连接配置 ==============
DB_FILE = "./test.db"
SQLITE_SYNC_URL = f"sqlite:///{DB_FILE}"
SQLITE_ASYNC_URL = f"sqlite+aiosqlite:///{DB_FILE}"

DATABASE_URL_TEST = os.getenv("DATABASE_URL_TEST", SQLITE_ASYNC_URL)
IS_PG = DATABASE_URL_TEST.startswith("postgresql")
ALEMBIC_SYNC_URL = (
    DATABASE_URL_TEST.replace("+asyncpg", "+psycopg")
    if DATABASE_URL_TEST.startswith("postgresql+asyncpg")
    else DATABASE_URL_TEST
)

if IS_PG:
    sync_engine = create_engine(ALEMBIC_SYNC_URL, future=True, pool_pre_ping=True)
else:
    sync_engine = create_engine(
        SQLITE_SYNC_URL,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 60},
    )

SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


def _import_all_models():
    from app.models.batch import Batch  # noqa
    from app.models.item import Item  # noqa
    from app.models.location import Location  # noqa
    from app.models.stock import Stock  # noqa
    from app.models.stock_ledger import StockLedger  # noqa
    from app.models.stock_snapshot import StockSnapshot  # noqa
    from app.models.warehouse import Warehouse  # noqa

    try:
        from app.models.order import Order, OrderItem  # noqa
    except Exception:
        pass


# ============== 会话级：重建测试库 → 迁移 → 兜底 ==============
@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    _import_all_models()

    if not IS_PG:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        Base.metadata.create_all(sync_engine)
    else:
        from alembic import command
        from alembic.config import Config

        url = make_url(ALEMBIC_SYNC_URL)
        target_db = url.database or "wms_test"
        admin_url = url.set(database="postgres")

        admin_eng = create_engine(
            admin_url.render_as_string(hide_password=False),
            future=True,
            isolation_level="AUTOCOMMIT",
            pool_pre_ping=True,
        )
        with admin_eng.connect() as conn:
            conn.execute(
                text(
                    """SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname=:d AND pid<>pg_backend_pid()"""
                ),
                {"d": target_db},
            )
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{target_db}"')
            owner = url.username or "postgres"
            conn.exec_driver_sql(f'CREATE DATABASE "{target_db}" OWNER "{owner}"')
        admin_eng.dispose()

        prev = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = ALEMBIC_SYNC_URL
        try:
            cfg = Config("alembic.ini")
            cfg.set_main_option("sqlalchemy.url", ALEMBIC_SYNC_URL)
            command.upgrade(cfg, "head")

            _import_all_models()
            ALLOW_CREATE = {
                "warehouses",
                "locations",
                "items",
                "batches",
                "stocks",
                "stock_ledger",
                "stock_snapshots",
            }
            for tbl in Base.metadata.sorted_tables:
                if tbl.name in ALLOW_CREATE:
                    tbl.create(sync_engine, checkfirst=True)
        finally:
            if prev is not None:
                os.environ["DATABASE_URL"] = prev
            else:
                os.environ.pop("DATABASE_URL", None)

    yield


# ============== 用例级：清表 + 预置维度 & 序列校正（PG） ==============
@pytest.fixture(autouse=True)
def _fresh_db():
    _import_all_models()

    if IS_PG:
        with sync_engine.begin() as conn:
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
            for tbl in target:
                if tbl in existing:
                    conn.execute(text(f'TRUNCATE TABLE "{tbl}" RESTART IDENTITY CASCADE'))

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
                for fld in (
                    "qty_available",
                    "qty_on_hand",
                    "qty_reserved",
                    "qty",
                    "min_qty",
                    "max_qty",
                ):
                    if hasattr(Item, fld) and getattr(itm, fld, None) is None:
                        setattr(itm, fld, 0)
                if hasattr(Item, "unit") and getattr(itm, "unit", None) is None:
                    itm.unit = "EA"
                s.add(itm)
            s.commit()
        finally:
            s.close()

        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('items','id'), GREATEST(COALESCE((SELECT MAX(id) FROM items),0),0)+1, false)"
                )
            )
            conn.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('locations','id'), GREATEST(COALESCE((SELECT MAX(id) FROM locations),0),0)+1, false)"
                )
            )
            conn.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('warehouses','id'), GREATEST(COALESCE((SELECT MAX(id) FROM warehouses),0),0)+1, false)"
                )
            )
    else:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
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
            conn.exec_driver_sql("INSERT INTO warehouses (id, name) VALUES (1, 'WH-TEST');")
            conn.exec_driver_sql(
                "INSERT INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-TEST', 1);"
            )

    yield


# ============== 异步会话工厂（NullPool+超时） ==============
def _make_async_session_factory():
    eng = create_async_engine(
        DATABASE_URL_TEST,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={
            "timeout": 10,
            "server_settings": {
                "statement_timeout": "15000",
                "idle_in_transaction_session_timeout": "15000",
            },
        },
        echo=False,
    )
    maker = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)
    return eng, maker


# ============== 同步 / 异步会话 ==============
@pytest.fixture()
def db():
    s = SyncSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest_asyncio.fixture()
async def session():
    eng, maker = _make_async_session_factory()
    try:
        async with maker() as s:
            yield s
    finally:
        await eng.dispose()


# ============== 依赖覆盖 ==============
@pytest.fixture(autouse=True)
def _override_get_session_globally():
    """仅覆盖异步依赖；同步依赖在 client 内按测试会话覆盖。"""
    from app.db.session import get_session

    async def _get_session_override():
        eng, maker = _make_async_session_factory()
        try:
            async with maker() as s:
                yield s
        finally:
            await eng.dispose()

    app.dependency_overrides[get_session] = _get_session_override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)


# ============== 双通道 HTTP 客户端（同步/异步皆可），并绑定同一同步会话 ==============
class _DualResponse:
    def __init__(self, sync_resp, async_coro_factory):
        self._sync = sync_resp
        self._acoro_factory = async_coro_factory

    def __getattr__(self, k):
        return getattr(self._sync, k)

    def __await__(self):
        async def _do():
            return await self._acoro_factory()

        return _do().__await__()


class _DualClient:
    def __init__(self, app_, db_session: Session):
        self._tc = TestClient(app_)
        self._ac = AsyncClient(transport=ASGITransport(app=app_), base_url="http://testserver")
        # 每个客户端实例都把 get_db 绑到“当前测试的同步 Session”
        from app.db.session import get_db

        def _get_db_override():
            yield db_session

        app_.dependency_overrides[get_db] = _get_db_override

    def get(self, *a, **kw):
        return self._tc.get(*a, **kw)

    def post(self, *a, **kw):
        sync_resp = self._tc.post(*a, **kw)

        async def _acoro():
            return await self._ac.post(*a, **kw)

        return _DualResponse(sync_resp, _acoro)

    async def aget(self, *a, **kw):
        return await self._ac.get(*a, **kw)

    async def apost(self, *a, **kw):
        return await self._ac.post(*a, **kw)

    async def aclose(self):
        await self._ac.aclose()

    def close(self):
        try:
            self._tc.close()
        finally:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except RuntimeError:
                pass


@pytest.fixture()
def client(db: Session):
    c = _DualClient(app, db_session=db)
    try:
        yield c
    finally:
        c.close()


# ============== ORM 方式最小维度（同步创建 + 提交） ==============
@pytest.fixture()
def item_loc_fixture(db: Session):
    from app.models.item import Item
    from app.models.location import Location
    from app.models.warehouse import Warehouse

    wh = db.query(Warehouse).filter_by(name="WH-TEST").first()
    if not wh:
        wh = Warehouse(name="WH-TEST")
        db.add(wh)
        db.flush()

    loc = db.query(Location).filter_by(name="LOC-TEST", warehouse_id=wh.id).first()
    if not loc:
        loc = Location(name="LOC-TEST", warehouse_id=wh.id)
        db.add(loc)
        db.flush()

    item = db.query(Item).filter_by(sku="SKU-TEST").first()
    if not item:
        item = Item(sku="SKU-TEST", name="测试商品")
        for fld in ("qty_available", "qty_on_hand", "qty_reserved", "qty", "min_qty", "max_qty"):
            if hasattr(Item, fld) and getattr(item, fld, None) is None:
                setattr(item, fld, 0)
        if hasattr(Item, "unit") and getattr(item, "unit", None) is None:
            item.unit = "EA"
        db.add(item)
        db.flush()

    db.commit()
    return (item.id, loc.id)


# ============== StockService 适配（异步入口薄封装） ==============
class StockServiceAsyncAdapter:
    def __init__(self, svc):
        self._svc = svc

    async def adjust(self, **kwargs):
        session = kwargs.pop("session")
        return await self._svc.adjust(session=session, **kwargs)


@pytest.fixture()
def stock_service(db: Session):
    from app.services.stock_service import StockService

    return StockServiceAsyncAdapter(StockService(db))


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as running with asyncio")
