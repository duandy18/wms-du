# app/api/routers/inbound_receipts.py
from app.wms.procurement.routers.inbound_receipts import po_receive_router, router

__all__ = ["router", "po_receive_router"]
