# app/wms/procurement/routers/purchase_orders_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.procurement.routers import purchase_orders_routes_core
from app.wms.procurement.routers import purchase_orders_routes_dev_demo
from app.wms.procurement.routers import purchase_orders_routes_list
from app.wms.procurement.routers import purchase_orders_routes_receive
from app.wms.procurement.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    purchase_orders_routes_core.register(router, svc)
    purchase_orders_routes_receive.register(router, svc)
    purchase_orders_routes_list.register(router, svc)
    purchase_orders_routes_dev_demo.register(router, svc)
