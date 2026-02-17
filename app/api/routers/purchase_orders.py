# app/api/routers/purchase_orders.py
"""
Purchase Orders Router（唯一入口，封板）

规则（硬）：
- 外部（尤其是 app/main.py）只能 include 本文件导出的 router。
- 任何 endpoint 实现都必须通过 register() 挂到此 router 上。
- 禁止直接 include / import “endpoints/endpoints-like” 模块里的 router（那些模块不应自行创建 router）。

目的：
- 避免重复挂载导致“同一路径多份实现 / 响应契约漂移”
- 保证 /purchase-orders 的行为与 response_model 契约单一且可追踪
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import purchase_orders_endpoints
from app.schemas.purchase_order import (
    PurchaseOrderCreateV2,
    PurchaseOrderReceiveLineIn,
    PurchaseOrderWithLinesOut,
)
from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

svc = PurchaseOrderService()


def _register_all_routes() -> None:
    # ✅ 唯一注册点：所有 /purchase-orders/* 的 endpoint 都从这里注册
    purchase_orders_endpoints.register(router, svc)


_register_all_routes()

__all__ = [
    "router",
    "svc",
    # re-export（便于 IDE / 其他模块引用 schema）
    "PurchaseOrderCreateV2",
    "PurchaseOrderReceiveLineIn",
    "PurchaseOrderWithLinesOut",
]
