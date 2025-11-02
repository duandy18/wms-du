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

# ======================================================
#  Database: per-request AsyncSession with NullPool
# ======================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms",
)

# 关键：使用 NullPool 防止在 pytest+httpx.ASGITransport 多事件循环下复用连接
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
#  Stubs for other routers (orders 等) 的依赖
#  仅为解决导入期依赖，测试不会真正调用这些函数。
#  如将来在路由里用到，再替换为真实实现即可。
# ======================================================

class _FakeUser(dict):
    """最小化的用户对象占位，满足 Depends 注入。"""
    @property
    def id(self) -> str:  # 兼容可能的属性访问
        return str(self.get("id", "test-user"))

async def get_current_user() -> _FakeUser:  # 可异步/同步均可，这里用异步以便通用
    # 在测试里不做鉴权，返回一个固定用户占位
    return _FakeUser(id="test-user", name="Test User")

class _OrderServiceStub:
    """最小化的订单服务占位，避免在应用启动时 ImportError。"""
    def __getattr__(self, name: str) -> Any:
        # 如果某路由真的调用到了这里的未实现方法，抛出更清晰的错误
        raise NotImplementedError(f"OrderService method '{name}' is not implemented in test stub.")

def get_order_service() -> _OrderServiceStub:
    # 作为 Depends 的工厂函数即可
    return _OrderServiceStub()
