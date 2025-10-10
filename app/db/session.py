# app/db/session.py
from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker


def _to_async_url(url: str) -> str:
    try:
        u = make_url(url)
    except Exception:
        return url

    drv = u.drivername
    if drv.endswith("+aiosqlite") or drv.endswith("+asyncpg") or drv.endswith("+aiomysql"):
        return url

    if drv == "sqlite":
        new = "sqlite+aiosqlite"
    elif drv in ("postgresql", "postgres"):
        new = "postgresql+asyncpg"
    elif drv == "mysql":
        new = "mysql+aiomysql"
    else:
        return url

    return re.sub(r"^[a-zA-Z0-9_+-]+", new, url, count=1)


# === 统一从环境读取数据库 URL（断开对 app.core.config 的依赖，避免循环导入） ===
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////home/andy-du/wms-du/dev.db")

# === 同步引擎（兼容老路由） ===
SYNC_ENGINE = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=SYNC_ENGINE, class_=Session, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# === 异步引擎（新路由 / 定时任务用） ===
ASYNC_DATABASE_URL = _to_async_url(DATABASE_URL)
ASYNC_ENGINE = create_async_engine(
    ASYNC_DATABASE_URL,
    future=True,
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=ASYNC_ENGINE, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# 兼容外部调用的别名（scheduler / services）
async_session_maker = AsyncSessionLocal


# 兼容 Alembic 旧用法
def get_database_url() -> str:
    return DATABASE_URL
