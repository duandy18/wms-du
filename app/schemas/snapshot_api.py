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


# ========= SnapshotPage：inventory 列表（事实切片行） =========
class InventoryRow(_Base):
    """
    ✅ Phase 2：事实口径（不可被破坏）

    每一行都是一个库存事实切片：
    - warehouse_id + item_id + batch_code
    - qty 为该切片在库数量（stocks.qty）
    """

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str, Field(min_length=0, max_length=128, description="商品名称")]

    item_code: Optional[str] = Field(default=None, description="商品编码（items.sku）")
    uom: Optional[str] = Field(default=None, description="单位（items.uom）")
    spec: Optional[str] = Field(default=None, description="规格（items.spec）")

    main_barcode: Optional[str] = Field(default=None, description="主条码（单值）")

    brand: Optional[str] = Field(default=None, description="品牌（预留字段）")
    category: Optional[str] = Field(default=None, description="品类（预留字段）")

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    batch_code: Optional[str] = Field(default=None, description="批次编码（可为空，前端展示 NO-BATCH）")

    qty: Annotated[int, Field(description="该切片数量（来自 stocks.qty）")]

    expiry_date: date | None = Field(default=None, description="该批次到期日（来自 batches.expiry_date）")
    near_expiry: bool = Field(default=False, description="该批次是否临期（未来 30 天内到期）")
    days_to_expiry: Optional[int] = Field(
        default=None, description="到期剩余天数（expiry_date - today；后端算，前端不推导）"
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
    - available_qty: 总可售（当前 = on_hand_qty）
    """

    on_hand_qty: Annotated[int, Field(ge=0, description="总在库数量")]
    available_qty: Annotated[int, Field(ge=0, description="总可售数量")]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "on_hand_qty": 270,
                "available_qty": 270,
            }
        }
    }


class ItemDetailSlice(_Base):
    """
    单条“仓 + 批次 + 数量”切片明细。
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
    available_qty: Annotated[int, Field(ge=0, description="可售数量")]

    near_expiry: bool = Field(default=False, description="该批次是否临期（未来 30 天内到期）")
    is_top: bool = Field(
        default=False,
        description="是否属于首页快照视图中的 Top2 切片（兼容历史字段，可保留）",
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
                        "available_qty": 100,
                        "near_expiry": False,
                        "is_top": True,
                    }
                ],
            }
        }
    }


__all__ = [
    "InventoryRow",
    "InventorySnapshotResponse",
    "ItemDetailTotals",
    "ItemDetailSlice",
    "ItemDetailResponse",
]
