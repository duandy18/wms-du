# app/wms/procurement/routers/purchase_orders_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.procurement.routers import purchase_orders_routes_completion
from app.procurement.routers import purchase_orders_routes_core
from app.procurement.routers import purchase_orders_routes_list
from app.procurement.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    # completion 必须先于 /{po_id} 注册，
    # 否则 /purchase-orders/completion 会被 /purchase-orders/{po_id} 吃掉并触发 422
    purchase_orders_routes_completion.register(router, svc)

    purchase_orders_routes_core.register(router, svc)
    purchase_orders_routes_list.register(router, svc)
