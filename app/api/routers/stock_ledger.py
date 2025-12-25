# app/api/routers/stock_ledger.py
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.routers import stock_ledger_routes_export
from app.api.routers import stock_ledger_routes_query
from app.api.routers import stock_ledger_routes_reconcile
from app.api.routers import stock_ledger_routes_summary
from app.api.routers.stock_ledger_helpers import (
    apply_common_filters_rows as _apply_common_filters_rows,
    build_base_ids_stmt as _build_base_ids_stmt,
    build_common_filters as _build_common_filters,
    infer_movement_type as _infer_movement_type,
    normalize_time_range as _normalize_time_range,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock/ledger", tags=["stock_ledger"])


def _register_all_routes() -> None:
    stock_ledger_routes_query.register(router)
    stock_ledger_routes_summary.register(router)
    stock_ledger_routes_reconcile.register(router)
    stock_ledger_routes_export.register(router)


_register_all_routes()

# 兼容：历史可能 import 这些工具函数名
__all__ = [
    "router",
    "_normalize_time_range",
    "_build_common_filters",
    "_infer_movement_type",
    "_build_base_ids_stmt",
    "_apply_common_filters_rows",
]
