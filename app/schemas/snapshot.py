# app/schemas/snapshot.py
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 模型直接序列化
    - extra="ignore": 忽略冗余字段（对旧客户端更宽容）
    - populate_by_name: 支持别名/字段名互填（便于以后加 alias）
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 快照运行结果 =========
class SnapshotRunResult(_Base):
    """
    执行单日库存快照后的结果
    """
    date: date
    affected_rows: Annotated[int, Field(ge=0, description="本次写入/更新的快照行数")] = 0

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"date": "2025-10-28", "affected_rows": 1234}
        }
    }


# ========= 快照读取模型 =========
class StockSnapshotRead(_Base):
    """
    单行快照读取模型
    - qty_on_hand: 账面库存
    - qty_allocated: 已分配（未出库）
    - qty_available: 可用（通常 = on_hand - allocated）
    """
    snapshot_date: date
    warehouse_id: int
    location_id: int
    item_id: int
    batch_id: int | None = None
    qty_on_hand: int
    qty_allocated: int
    qty_available: int
    expiry_date: date | None = None
    age_days: int | None = None
    created_at: datetime | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "snapshot_date": "2025-10-28",
                "warehouse_id": 1,
                "location_id": 101,
                "item_id": 777,
                "batch_id": 3456,
                "qty_on_hand": 150,
                "qty_allocated": 20,
                "qty_available": 130,
                "expiry_date": "2026-04-01",
                "age_days": 27,
                "created_at": "2025-10-28T00:05:00Z",
            }
        }
    }


# ========= 趋势点（用于 /snapshot/trends） =========
class TrendPoint(_Base):
    """
    库存趋势图数据点（按日聚合）
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


__all__ = ["SnapshotRunResult", "StockSnapshotRead", "TrendPoint"]
