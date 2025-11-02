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
    # 若其它路由需要，按需在此补充导出
]

# ======================================================
# Database: per-request AsyncSession with NullPool
# ======================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms",
)

# 关键：使用 NullPool，避免在 pytest + httpx.ASGITransport 多事件循环下复用连接
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    future=True,
)

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
    - 始终 close，避免 GC 清理未归还连接的 SAWarning。
    """
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


# ======================================================
# Stubs for other routers (orders 等) 的依赖
# 仅为解决导入期依赖；如路由后续真的调用，再替换为真实实现。
# ======================================================

class _FakeUser(dict):
    """最小化的用户对象占位，满足 Depends 注入。"""
    @property
    def id(self) -> str:
        return str(self.get("id", "test-user"))

async def get_current_user() -> _FakeUser:
    """测试环境不做鉴权，返回固定用户占位。"""
    return _FakeUser(id="test-user", name="Test User")

class _OrderServiceStub:
    """最小化的订单服务占位，避免应用启动时 ImportError。"""
    def __getattr__(self, name: str) -> Any:
        raise NotImplementedError(
            f"OrderService method '{name}' is not implemented in test stub."
        )

def get_order_service() -> _OrderServiceStub:
    """作为 Depends 工厂函数返回占位服务。"""
    return _OrderServiceStub()
