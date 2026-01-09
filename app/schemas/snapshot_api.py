from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

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


# ========= SnapshotPage：inventory 列表 =========
class InventoryTopLocation(_Base):
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    batch_code: Annotated[str, Field(min_length=1, max_length=64, description="批次编码")]
    qty: Annotated[int, Field(description="该切片数量（来自 stocks.qty）")]


class InventoryRow(_Base):
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str, Field(min_length=0, max_length=128, description="商品名称")]

    # ✅ 商品主数据（真实来源：items）
    item_code: Optional[str] = Field(default=None, description="商品编码（items.sku）")
    uom: Optional[str] = Field(default=None, description="单位（items.unit）")
    spec: Optional[str] = Field(default=None, description="规格（items.spec）")

    # ✅ 单值条码（避免一对多 join 放大）
    main_barcode: Optional[str] = Field(default=None, description="主条码（单值）")

    # 预留字段：当前 items 未落库，先兼容前端展示
    brand: Optional[str] = Field(default=None, description="品牌（预留字段）")
    category: Optional[str] = Field(default=None, description="品类（预留字段）")

    total_qty: Annotated[int, Field(description="总库存（按 item 聚合的 stocks.qty 之和）")]
    top2_locations: list[InventoryTopLocation] = Field(default_factory=list)

    earliest_expiry: date | None = Field(default=None, description="最早到期日")
    near_expiry: bool = Field(default=False, description="是否临期（未来 30 天内到期）")

    # ✅ 后端统一计算，前端不推导
    days_to_expiry: Optional[int] = Field(
        default=None, description="最早到期剩余天数（earliest_expiry - today）"
    )


class InventorySnapshotResponse(_Base):
    total: Annotated[int, Field(ge=0)]
    offset: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    rows: list[InventoryRow] = Field(default_factory=list)


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
    "InventoryTopLocation",
    "InventoryRow",
    "InventorySnapshotResponse",
    "ItemDetailTotals",
    "ItemDetailSlice",
    "ItemDetailResponse",
]
