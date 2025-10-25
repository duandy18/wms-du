# tests/conftest.py
import os
import asyncio
import contextlib
import pytest
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Alembic programmatic API（在会话开始时把 DB 升到 head）
from alembic.config import Config
from alembic import command

# HTTP 测试（若你的用例依赖 HTTP 层）
try:
    from httpx import AsyncClient, ASGITransport
    HAVE_HTTPX = True
except Exception:
    HAVE_HTTPX = False

# 同步 TestClient（供 tests 里直接使用 client.get()/post()）
try:
    from starlette.testclient import TestClient
    HAVE_TESTCLIENT = True
except Exception:
    HAVE_TESTCLIENT = False


# ------------------------------
# 0) 统一解析数据库 URL（异步驱动）
# ------------------------------
def _async_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    return url.replace("+psycopg", "+asyncpg")


# ------------------------------
# 1) 会话级：自动迁移到 head（如遇多头兜底到 heads）
# ------------------------------
@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    # 统一系统时区到 Asia/Shanghai（UTC+8）
    os.environ.setdefault("TZ", "Asia/Shanghai")

    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"),
    )
    try:
        command.upgrade(cfg, "head")
    except Exception:
        # 极少数场景（历史遗留多 head），兜底到 heads，保证测试可跑
        command.upgrade(cfg, "heads")


# ------------------------------
# 2) 函数级异步引擎/会话工厂（避免不同 loop 冲突）
# ------------------------------
@pytest.fixture(scope="function")
def async_engine() -> AsyncEngine:
    """
    函数级 engine：与每条测试用例的 event loop 生命周期一致，
    杜绝 'Future attached to a different loop'。
    """
    return create_async_engine(_async_db_url(), future=True, pool_pre_ping=True)


@pytest.fixture(scope="function")
def async_session_maker(async_engine: AsyncEngine):
    """函数级会话工厂。部分用例会自己 new session 并 commit。"""
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def session(async_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """
    函数级事务会话：每条用例独立事务，结束时回滚，保证隔离。
    进入事务后，显式设置本地时区为 Asia/Shanghai（UTC+8）。
    """
    async with async_session_maker() as sess:
        trans = await sess.begin()
        try:
            # 关键：会话级事务里固定时区（不会影响其它连接）
            await sess.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
            yield sess
        finally:
            with contextlib.suppress(Exception):
                await trans.rollback()
            with contextlib.suppress(Exception):
                await sess.close()


# ------------------------------
# 3) HTTP 客户端（异步 & 同步）
# ------------------------------
@pytest.fixture(scope="function")
async def ac():
    """
    httpx.AsyncClient（ASGITransport）。
    若你的项目 app 入口路径不同，请把 import 改为实际路径。
    """
    if not HAVE_HTTPX:
        pytest.skip("httpx not installed")
    from app.main import app  # 若路径不同，改成你的应用入口
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def client():
    """
    starlette.testclient.TestClient（同步）。
    供 tests/services/* 里直接 client.get()/post() 使用。
    """
    if not HAVE_TESTCLIENT:
        pytest.skip("starlette TestClient not available")
    from app.main import app  # 若路径不同，改成你的应用入口
    with TestClient(app) as tc:
        yield tc


# 提供 stock_service fixture（tests 里直接依赖）
@pytest.fixture(scope="function")
def stock_service():
    from app.services.stock_service import StockService
    return StockService()


# 供服务层用例造基线 item/location（避免缺失的 item_loc_fixture）
@pytest.fixture
async def item_loc_fixture(session):
    """
    提供一个干净的 item_id/location_id 组合给服务类用例。
    由于前置已 RESTART IDENTITY，这里固定插入 id=1 即可。
    """
    # items(id=1)
    await session.execute(text("INSERT INTO items (id, name, sku) VALUES (1, 'UT-ITEM', 'UT-1')"))
    # locations(id=1) —— 依赖前置 _db_clean 已回种 warehouses(id=1,'WH-1')
    await session.execute(
        text("INSERT INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-1', 1)")
    )
    await session.commit()
    return 1, 1


# ------------------------------
# 4) 每条用例开始前的“强力清表 + 基线回种”
# ------------------------------
@pytest.fixture(autouse=True, scope="function")
async def _db_clean(async_engine: AsyncEngine):
    """
    使用 TRUNCATE ... RESTART IDENTITY CASCADE（PostgreSQL）重置主键与外键，
    避免固定主键插入（如 batches.id=32001）在重复运行中撞车。
    SQLite 分支回退到 DELETE 并清空 sqlite_sequence。
    最后回种 warehouses(id=1,'WH-1') 作为外键基线。
    """
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name

        if dialect == "postgresql":
            # 先尝试 TRUNCATE + RESTART IDENTITY + CASCADE
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
            # SQLite 等：逐表 DELETE，并尽量重置自增序列
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
            # 尝试清空自增序列
            with contextlib.suppress(Exception):
                await conn.execute(text("DELETE FROM sqlite_sequence;"))

        # 基线维度回种（关键）：仓库表必须有 id=1，供 locations(..., warehouse_id=1) 外键引用
        await conn.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
        )


# ------------------------------
# 5) pytest-asyncio loop（会话级）
# ------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """为 pytest-asyncio 提供一个会话级 event loop。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
