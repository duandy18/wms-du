# app/api/deps.py
from __future__ import annotations

import os
from typing import AsyncGenerator, Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

__all__ = [
    "get_session",
    "get_current_user",
    "get_order_service",
    "DATABASE_URL",
]

# ------------------------------------------------------
# DB 基础配置（NullPool + 每请求独立 Session）
# ------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,   # 关键：禁止连接复用，避免多事件循环下的 asyncpg 并发报错
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = SessionLocal()
    try:
        yield session
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            pass


# ------------------------------------------------------
# 其它路由依赖的占位（orders 等）
# ------------------------------------------------------
class _FakeUser(dict):
    @property
    def id(self) -> str:
        return str(self.get("id", "test-user"))

async def get_current_user() -> _FakeUser:
    return _FakeUser(id="test-user", name="Test User")

class _OrderServiceStub:
    def __getattr__(self, name: str) -> Any:
        raise NotImplementedError(
            f"OrderService method '{name}' is not implemented in test stub."
        )

def get_order_service() -> _OrderServiceStub:
    return _OrderServiceStub()
