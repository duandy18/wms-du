# app/services/stock/accessors.py
from __future__ import annotations

from sqlalchemy import literal

from app.models.batch import Batch
from app.models.stock import Stock


def stock_qty_col():
    col = getattr(Stock, "qty", None)
    if col is None:
        raise AssertionError("stocks 缺少 qty 列")
    return col


def batch_qty_col():
    """
    兼容：若 Batch 没有 qty 列，则返回常量 0（仅用于查询/表达式场景）。
    注意：INSERT/UPDATE 时请先判断 hasattr(Batch, 'qty') 再写入。
    """
    col = getattr(Batch, "qty", None)
    if col is None:
        return literal(0).label("qty")
    return col


def batch_code_attr():
    col = getattr(Batch, "batch_code", None)
    if col is None:
        raise AssertionError("batches 缺少 batch_code 列")
    return col
