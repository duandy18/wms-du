# app/api/routers/purchase_reports.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import purchase_reports_routes_daily
from app.api.routers import purchase_reports_routes_items
from app.api.routers import purchase_reports_routes_suppliers
from app.api.routers.purchase_reports_helpers import apply_common_filters as _apply_common_filters

router = APIRouter(prefix="/purchase-reports", tags=["purchase-reports"])


def _register_all_routes() -> None:
    purchase_reports_routes_suppliers.register(router)
    purchase_reports_routes_items.register(router)
    purchase_reports_routes_daily.register(router)


_register_all_routes()

# 兼容：历史 import 可能依赖这个名字
__all__ = ["router", "_apply_common_filters"]
