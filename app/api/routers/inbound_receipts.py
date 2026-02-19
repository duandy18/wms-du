# app/api/routers/inbound_receipts.py
from __future__ import annotations

from app.api.routers.inbound_receipts_routes import router
from app.api.routers.purchase_orders_receive_routes import po_receive_router

__all__ = ["router", "po_receive_router"]
