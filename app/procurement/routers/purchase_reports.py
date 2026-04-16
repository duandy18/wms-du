# app/procurement/routers/purchase_reports.py
from __future__ import annotations

from fastapi import APIRouter

from app.procurement.routers import purchase_reports_routes_daily
from app.procurement.routers import purchase_reports_routes_item_lines
from app.procurement.routers import purchase_reports_routes_items
from app.procurement.routers import purchase_reports_routes_summary
from app.procurement.routers import purchase_reports_routes_suppliers

router = APIRouter(prefix="/purchase-reports", tags=["purchase-reports"])


def _register_all_routes() -> None:
    purchase_reports_routes_summary.register(router)
    purchase_reports_routes_suppliers.register(router)
    purchase_reports_routes_item_lines.register(router)
    purchase_reports_routes_items.register(router)
    purchase_reports_routes_daily.register(router)


_register_all_routes()

__all__ = ["router"]
