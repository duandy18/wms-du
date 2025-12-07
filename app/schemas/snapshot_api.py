from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """
    Snapshot API 专用模型基类。
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= Drawer V2：单个商品仓+批次明细 =========
class ItemDetailTotals(_Base):
    """
    /snapshot/item-detail 的 totals 区汇总：
    - on_hand_qty: 总在库
    - reserved_qty: 总锁定
    - available_qty: 总可售（当前 = on_hand_qty，预留给后续扣减逻辑）
    """

    on_hand_qty: Annotated[int, Field(ge=0, description="总在库数量")]
    reserved_qty: Annotated[int, Field(ge=0, description="总锁定数量")] = 0
    available_qty: Annotated[int, Field(ge=0, description="总可售数量")]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "on_hand_qty": 270,
                "reserved_qty": 0,
                "available_qty": 270,
            }
        }
    }


class ItemDetailSlice(_Base):
    """
    单条“仓 + 批次 + 数量”切片明细。

    注意：日期字段统一使用 production_date / expiry_date，
    与 batches / ledger / FEFO 链路保持一致。
    """

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name: Annotated[str, Field(min_length=1, max_length=100, description="仓库名称")]
    pool: Annotated[
        str,
        Field(
            min_length=1,
            max_length=32,
            description="库存池（MAIN / RETURNS / QUARANTINE 等，当前阶段默认 MAIN）",
        ),
    ]
    batch_code: Annotated[str, Field(min_length=1, max_length=64, description="批次编码")]

    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日")

    on_hand_qty: Annotated[int, Field(ge=0, description="在库数量")]
    reserved_qty: Annotated[int, Field(ge=0, description="锁定数量")] = 0
    available_qty: Annotated[int, Field(ge=0, description="可售数量")]

    near_expiry: bool = Field(default=False, description="该批次是否临期（未来 30 天内到期）")
    is_top: bool = Field(
        default=False,
        description="是否属于首页快照视图中的 Top2 切片",
    )

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "warehouse_id": 1,
                "warehouse_name": "WH-1 MAIN",
                "pool": "MAIN",
                "batch_code": "B2025-01-A",
                "production_date": "2025-01-01",
                "expiry_date": "2026-07-01",
                "on_hand_qty": 100,
                "reserved_qty": 0,
                "available_qty": 100,
                "near_expiry": False,
                "is_top": True,
            }
        }
    }


class ItemDetailResponse(_Base):
    """
    Drawer V2：单个商品的全量“仓 + 批次”库存明细
    """

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str, Field(min_length=0, max_length=128, description="商品名称")]

    totals: ItemDetailTotals
    slices: list[ItemDetailSlice]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_id": 777,
                "item_name": "顽皮双拼猫粮 1.5kg",
                "totals": {
                    "on_hand_qty": 270,
                    "reserved_qty": 0,
                    "available_qty": 270,
                },
                "slices": [
                    {
                        "warehouse_id": 1,
                        "warehouse_name": "WH-1 MAIN",
                        "pool": "MAIN",
                        "batch_code": "B2025-01-A",
                        "production_date": "2025-01-01",
                        "expiry_date": "2026-07-01",
                        "on_hand_qty": 100,
                        "reserved_qty": 0,
                        "available_qty": 100,
                        "near_expiry": False,
                        "is_top": True,
                    }
                ],
            }
        }
    }


__all__ = [
    "ItemDetailTotals",
    "ItemDetailSlice",
    "ItemDetailResponse",
]
