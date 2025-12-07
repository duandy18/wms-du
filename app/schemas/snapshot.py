from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """
    snapshot 相关模型的通用基类。
    目前仅保留 TrendPoint，用于未来基于 stocks 的趋势分析。
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class TrendPoint(_Base):
    """
    库存趋势图数据点（按日聚合）。
    当前并未直接被 /snapshot 路由使用，保留作为将来扩展的类型。
    """

    snapshot_date: date
    qty_on_hand: int
    qty_available: int

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "snapshot_date": "2025-10-28",
                "qty_on_hand": 1500,
                "qty_available": 1320,
            }
        }
    }


__all__ = ["TrendPoint"]
