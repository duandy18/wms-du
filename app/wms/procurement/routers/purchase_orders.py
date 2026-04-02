# app/wms/procurement/routers/purchase_orders.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.procurement.routers import purchase_orders_endpoints
from app.schemas.purchase_order import (
    PurchaseOrderCreateV2,
    PurchaseOrderReceiveLineIn,
    PurchaseOrderWithLinesOut,
)
from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

svc = PurchaseOrderService()


def _register_all_routes() -> None:
    purchase_orders_endpoints.register(router, svc)


_register_all_routes()

__all__ = [
    "router",
    "svc",
    "PurchaseOrderCreateV2",
    "PurchaseOrderReceiveLineIn",
    "PurchaseOrderWithLinesOut",
]
