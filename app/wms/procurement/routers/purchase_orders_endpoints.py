# app/wms/procurement/routers/purchase_orders_endpoints.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.procurement.routers import purchase_orders_endpoints_core
from app.wms.procurement.routers import purchase_orders_endpoints_dev_demo
from app.wms.procurement.routers import purchase_orders_endpoints_list
from app.wms.procurement.routers import purchase_orders_endpoints_receive
from app.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    purchase_orders_endpoints_core.register(router, svc)
    purchase_orders_endpoints_receive.register(router, svc)
    purchase_orders_endpoints_list.register(router, svc)
    purchase_orders_endpoints_dev_demo.register(router, svc)
