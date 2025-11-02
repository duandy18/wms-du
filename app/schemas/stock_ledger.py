# app/schemas/stock_ledger.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 可选：若你希望返回枚举类型，可解开下面的导入并把 LedgerRow.movement_type 从 str 改为 MovementType
# from app.models.enums import MovementType


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名/字段名互填（便于未来演进）
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 查询入参 =========
class LedgerQuery(_Base):
    """
    台账查询（支持按 stock_id / batch_code / reason / ref 过滤，带时间区间与分页）
    """
    stock_id: int | None = Field(default=None, ge=1, description="stocks.id")
    batch_code: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=200)
    ref: str | None = Field(default=None, max_length=128)

    time_from: datetime | None = None
    time_to: datetime | None = None

    # 分页
    limit: Annotated[int, Field(default=100, ge=1, le=1000)] = 100
    offset: Annotated[int, Field(default=0, ge=0)] = 0

    @field_validator("batch_code", "reason", "ref", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("time_to")
    @classmethod
    def _time_range_valid(cls, v: datetime | None, info):
        t_from: datetime | None = info.data.get("time_from")
        if v is not None and t_from is not None and v < t_from:
            raise ValueError("time_to 必须 >= time_from")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "stock_id": 123,
                "batch_code": "B-20251028-A",
                "reason": "RECEIPT",
                "ref": "PO-202510-0001",
                "time_from": "2025-10-01T00:00:00Z",
                "time_to": "2025-10-31T23:59:59Z",
                "limit": 100,
                "offset": 0,
            }
        }
    }


# ========= 明细行 =========
class LedgerRow(_Base):
    """
    单条库存台账记录
    - delta: 本次变动量（正数=入库，负数=出库）
    - after_qty: 本条记录执行后的库存结余
    """
    id: int
    stock_id: int
    batch_id: int | None = None

    delta: int
    reason: str
    ref: str | None = None

    created_at: datetime
    after_qty: int

    # 如需返回业务枚举，可换成：
    # movement_type: MovementType | None = None
    movement_type: str | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": 10001,
                "stock_id": 123,
                "batch_id": 456,
                "delta": 10,
                "reason": "RECEIPT",
                "ref": "PO-202510-0001#1",
                "created_at": "2025-10-28T10:00:00Z",
                "after_qty": 120,
                "movement_type": "receipt",
            }
        }
    }


# ========= 列表返回 =========
class LedgerList(_Base):
    """
    台账列表响应
    """
    total: Annotated[int, Field(ge=0)]
    items: list[LedgerRow] = Field(default_factory=list)

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "total": 2,
                "items": [
                    {
                        "id": 10001,
                        "stock_id": 123,
                        "batch_id": 456,
                        "delta": 10,
                        "reason": "RECEIPT",
                        "ref": "PO-202510-0001#1",
                        "created_at": "2025-10-28T10:00:00Z",
                        "after_qty": 120,
                        "movement_type": "receipt",
                    },
                    {
                        "id": 10002,
                        "stock_id": 123,
                        "batch_id": 456,
                        "delta": -4,
                        "reason": "SHIPMENT",
                        "ref": "SO-202510-0002#1",
                        "created_at": "2025-10-28T14:30:00Z",
                        "after_qty": 116,
                        "movement_type": "shipment",
                    },
                ],
            }
        }
    }


__all__ = ["LedgerQuery", "LedgerRow", "LedgerList"]
