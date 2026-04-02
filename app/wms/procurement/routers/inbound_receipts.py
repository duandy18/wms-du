# app/wms/procurement/routers/inbound_receipts.py
from __future__ import annotations

from app.wms.procurement.routers.inbound_receipts_routes import router
from app.wms.procurement.routers.purchase_orders_receive_routes import po_receive_router

__all__ = ["router", "po_receive_router"]
