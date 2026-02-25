# app/services/stock/accessors.py
from __future__ import annotations

from sqlalchemy import literal


def _phase4e_legacy_disabled(name: str) -> None:
    raise RuntimeError(
        f"Phase 4E: legacy stocks accessor '{name}' 已禁用。"
        "禁止读取 legacy stocks 或 legacy 批次表；请改用 lot-world（stocks_lot + lots）口径。"
    )


def stock_qty_col():
    """
    旧时代：返回 Stock.qty 列（stocks 世界）。
    Phase 4E：禁用（禁止任何执行路径触碰 legacy stocks）。
    """
    _phase4e_legacy_disabled("stock_qty_col")


def batch_qty_col():
    """
    旧时代：返回批次数量列（表达式场景）。
    Phase 4E：禁用（批次实体已迁移到 lots，数量来自 stocks_lot）。
    """
    _phase4e_legacy_disabled("batch_qty_col")
    return literal(0).label("qty")


def batch_code_attr():
    """
    旧时代：返回批次编码属性。
    Phase 4E：禁用（批次 canonical 已迁移到 lots）。
    """
    _phase4e_legacy_disabled("batch_code_attr")
