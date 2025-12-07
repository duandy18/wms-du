# app/db/session.py
# 统一的同步/异步会话工厂 + FastAPI 依赖（get_db / get_session / get_async_session）
from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine as create_sync_engine_sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker


# ---- DSN 归一：把 sync/async DSN 统一到 psycopg3 与 aiosqlite ----
def _normalize_sync_dsn(url: str) -> str:
    if not url:
        # 默认使用 dev 环境 PG（5433）
        return "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"
    # postgres/postgresql(+*) → postgresql+psycopg
    if url.startswith("postgresql+asyncpg://") or url.startswith("postgres+asyncpg://"):
        return re.sub(r"^postgres(?:ql)?\+asyncpg://", "postgresql+psycopg://", url)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _normalize_async_dsn(url: str) -> str:
    if not url:
        # 默认使用 dev 环境 PG（5433）
        return "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"
    # sqlite:/// → sqlite+aiosqlite:///
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite://" + url[len("sqlite:///") - 1 :]
    # postgres/postgresql(+*) → postgresql+psycopg
    if url.startswith("postgresql+asyncpg://") or url.startswith("postgres+asyncpg://"):
        return re.sub(r"^postgres(?:ql)?\+asyncpg://", "postgresql+psycopg://", url)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# 优先级：
#  1) WMS_DATABASE_URL（你用来跑 Alembic / 本地 docker 的）
#  2) DATABASE_URL
#  3) 默认 dev DSN: 5433/wms
_DEFAULT_DSN = "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"
_raw = os.getenv("WMS_DATABASE_URL") or os.getenv("DATABASE_URL") or _DEFAULT_DSN

# 有些环境会把值写成 '"postgresql+psycopg://.../wms"'，这里统一剥掉两侧引号
_raw = _raw.strip()
if (_raw.startswith('"') and _raw.endswith('"')) or (_raw.startswith("'") and _raw.endswith("'")):
    _raw = _raw[1:-1].strip()

RAW_URL = _raw

SYNC_URL = _normalize_sync_dsn(RAW_URL)
ASYNC_URL = _normalize_async_dsn(RAW_URL)

print(f"[DB] Using DSN (sync) : {SYNC_URL}")
print(f"[DB] Using DSN (async): {ASYNC_URL}")

# ---- 同步 Engine + Session（Alembic / 同步场景） ----
engine = create_sync_engine_sa(SYNC_URL, future=True, pool_pre_ping=True)
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)

# ---- 异步 Engine + AsyncSession（FastAPI / 异步服务） ----
# 关键修复：PG (psycopg3) 下不传 connect_args['server_settings']；统一空 dict
_async_connect_args = {}
async_engine: AsyncEngine = create_async_engine(
    ASYNC_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=_async_connect_args,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 对外兼容的别名
async_session_maker = AsyncSessionLocal  # 常见历史引用


# ---- FastAPI 依赖 ----
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# 兼容历史命名
get_async_session = get_session


# ---- 关闭引擎（测试/生命周期） ----
async def close_engines() -> None:
    await async_engine.dispose()
    engine.dispose()
