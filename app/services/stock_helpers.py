# app/services/stock_helpers.py
"""
Legacy shim (库存辅助入口)

- 项目已进入 warehouse 主维度世界观（以 warehouse_id 为核心维度）。
- 本模块仅做薄封装，统一从 stock_helpers_impl re-export
"""

from __future__ import annotations

from app.services.stock_helpers_impl import (
    batch_code_attr,
    batch_qty_col,
    bump_stock,
    bump_stock_by_stock_id,
    ensure_batch_full,
    ensure_item,
    ensure_stock_row,
    ensure_stock_slot,
    exec_retry,
    get_current_qty,
    stock_qty_col,
)

__all__ = [
    "exec_retry",
    "stock_qty_col",
    "batch_qty_col",
    "batch_code_attr",
    "ensure_item",
    "ensure_stock_slot",
    "ensure_stock_row",
    "bump_stock_by_stock_id",
    "bump_stock",
    "get_current_qty",
    "ensure_batch_full",
]
