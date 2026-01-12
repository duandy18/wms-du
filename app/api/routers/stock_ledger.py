# app/api/routers/stock_ledger.py
from __future__ import annotations

import logging
from fastapi import APIRouter

from app.api.routers import (
    stock_ledger_routes_query,
    stock_ledger_routes_query_history,
    stock_ledger_routes_summary,
    stock_ledger_routes_reconcile,
    stock_ledger_routes_export,
)

logger = logging.getLogger(__name__)

# 统一前缀
router = APIRouter(prefix="/stock/ledger", tags=["stock_ledger"])


def _register_all_routes() -> None:
    """
    库存台账相关路由聚合点（唯一）：

    - /query            ≤90 天普通查询
    - /query-history    >90 天历史查询（强约束）
    - /summary          统计
    - /reconcile        对账
    - /export           导出
    """
    stock_ledger_routes_query.register(router)
    stock_ledger_routes_query_history.register(router)
    stock_ledger_routes_summary.register(router)
    stock_ledger_routes_reconcile.register(router)
    stock_ledger_routes_export.register(router)


_register_all_routes()

__all__ = ["router"]
