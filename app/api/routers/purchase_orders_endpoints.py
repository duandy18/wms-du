# app/api/routers/purchase_orders_endpoints.py
"""
Purchase Orders Endpoints（内部模块，封板）

说明：
- 本文件只负责聚合注册，不承载大段 endpoint 实现
- 具体实现按职责拆分到：
  - purchase_orders_endpoints_core.py（create/get/close/receipts）
  - purchase_orders_endpoints_receive.py（receive-line + 执行硬阻断）
  - purchase_orders_endpoints_list.py（list）
  - purchase_orders_endpoints_dev_demo.py（dev-demo）
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import purchase_orders_endpoints_core
from app.api.routers import purchase_orders_endpoints_dev_demo
from app.api.routers import purchase_orders_endpoints_list
from app.api.routers import purchase_orders_endpoints_receive
from app.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    purchase_orders_endpoints_core.register(router, svc)
    purchase_orders_endpoints_receive.register(router, svc)
    purchase_orders_endpoints_list.register(router, svc)
    purchase_orders_endpoints_dev_demo.register(router, svc)
