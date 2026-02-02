from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """
    snapshot 相关模型的通用基类。
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class TrendPoint(_Base):
    """
    库存趋势图数据点（按日聚合）。

    ✅ Stage C.2：对外契约统一使用 qty
    - qty            : 当日库存事实（与 stocks.qty / stock_snapshots.qty 语义一致）
    - qty_available  : 可用量（当前阶段等同 qty，后续可引入分配逻辑）
    """

    snapshot_date: date
    qty: int
    qty_available: int

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "snapshot_date": "2025-10-28",
                "qty": 1500,
                "qty_available": 1320,
            }
        }
    }


__all__ = ["TrendPoint"]
