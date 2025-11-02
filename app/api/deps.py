# app/api/deps.py
from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# 1) 连接串：CI / 本地均可通过环境变量覆盖
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms",
)

# 2) 关键：NullPool 避免连接在不同事件循环复用（pytest 多次起落 + httpx.ASGITransport）
#    另外 disable_for_update=True 可减少 asyncpg 的状态机交叉。
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    future=True,
)

# 3) 统一会话工厂：expire_on_commit=False 以便提交后对象仍可用
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖：每请求独立会话。
    - 失败自动 rollback；
    - 始终 close，避免“GC 清理未归还连接”的 SAWarning。
    """
    session: AsyncSession = SessionLocal()
    try:
        yield session
        # 由调用方决定是否 commit；路由中显式 commit 后，这里不再自动提交
    except Exception:
        # 避免“另一个操作进行中”的典型做法：错误即回滚，清理事务状态。
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
