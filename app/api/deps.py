# app/api/deps.py
from __future__ import annotations

from typing import Any, AsyncGenerator

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

# ---------------------------
# 基础依赖：DB / Settings
# ---------------------------


def get_db_session(db: Session = Depends(get_db)) -> Session:
    """统一对外暴露的同步 DB 会话依赖（用于同步 Service）。"""
    return db


def get_settings_dep():
    """给端点/服务读取配置用的依赖（便于测试替换）。"""
    return get_settings()


# ---------------------------
# Service 装配（延迟导入，防环）
# ---------------------------


def get_stock_service(db: Session = Depends(get_db_session)):
    """延迟导入可避免启动期循环依赖。"""
    from app.services.stock_service import StockService

    return StockService(db=db)


def get_order_service(db: Session = Depends(get_db_session)):
    from app.services.order_service import OrderService

    return OrderService(db=db)


# ---------------------------
# 分页解析（统一入参/出参）
# ---------------------------


class PaginationParams(BaseModel):
    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return max(self.page - 1, 0) * self.size


def get_pagination(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    size: int = Query(20, ge=1, le=200, description="每页条数，1-200"),
) -> PaginationParams:
    return PaginationParams(page=page, size=size)


# ---------------------------
# 开发期鉴权 Stub（待替换为 JWT）
# ---------------------------


def get_current_user() -> dict[str, Any]:
    """
    开发期 stub：总是返回一个固定的“已登录用户”。
    生产环境请用 JWT / 会话验证替换本函数（保持同名签名即可）。
    """
    return {"id": 0, "username": "local-dev", "roles": ["admin"]}


# ---------------------------
# 异步会话依赖（routers 使用）
# ---------------------------


try:
    # 优先使用项目提供的异步会话工厂
    from app.db.session import get_session as _project_get_async_session
except Exception:
    _project_get_async_session = None  # type: ignore


async def get_session() -> AsyncGenerator["AsyncSession", None]:
    """
    统一给 routers 使用的异步会话依赖。
    - 从 app.db.session.get_session 获取 AsyncSession
    - 如无该工厂，则抛出明确错误提示
    """
    if _project_get_async_session is None:
        raise RuntimeError(
            "Async session factory not found. "
            "Please ensure app.db.session.get_session (async) exists."
        )
    async for s in _project_get_async_session():
        yield s


# 历史别名兼容
get_async_session = get_session
