# app/api/deps.py
from __future__ import annotations

from typing import Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

# ---------------------------
# 基础依赖：DB / Settings
# ---------------------------


def get_db_session(db: Session = Depends(get_db)) -> Session:
    """统一对外暴露的 DB 会话依赖。"""
    return db


def get_settings_dep():
    """给端点/服务读取配置用的依赖（便于测试替换）。"""
    return get_settings()


# ---------------------------
# Service 装配（延迟导入，防环）
# ---------------------------


def get_stock_service(db: Session = Depends(get_db_session)):
    # 延迟导入可避免启动期的循环依赖
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
