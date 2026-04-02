from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """
    stock 展示接口专用模型基类。
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class InventoryRow(_Base):
    """
    库存总览中的单条事实切片行。

    每一行表示一个实时库存切片：
    - warehouse_id + item_id + lot（展示码为 lots.lot_code，可为 NULL）
    - qty 为该切片在库数量（来自 stocks_lot.qty 的聚合口径）

    兼容说明：
    - lot_code 为正名
    - batch_code 为兼容字段（等价于 lot_code）
    """

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str, Field(min_length=0, max_length=128, description="商品名称")]

    item_code: Optional[str] = Field(default=None, description="商品编码（items.sku）")
    spec: Optional[str] = Field(default=None, description="规格（items.spec）")

    main_barcode: Optional[str] = Field(default=None, description="主条码（单值）")

    brand: Optional[str] = Field(default=None, description="品牌（预留字段）")
    category: Optional[str] = Field(default=None, description="品类（预留字段）")

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    lot_code: Optional[str] = Field(default=None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(default=None, description="批次编码（兼容字段；等价于 lot_code）")

    qty: Annotated[int, Field(description="该切片数量（来自 stocks_lot.qty）")]

    expiry_date: date | None = Field(default=None, description="该批次到期日")
    near_expiry: bool = Field(default=False, description="该批次是否临期（未来 30 天内到期）")
    days_to_expiry: Optional[int] = Field(default=None, description="到期剩余天数（expiry_date - today；后端算，前端不推导）")


class InventoryDisplayResponse(_Base):
    total: Annotated[int, Field(ge=0)]
    offset: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    rows: list[InventoryRow] = Field(default_factory=list)


class ItemDetailTotals(_Base):
    """
    单品库存明细 totals 区汇总：
    - on_hand_qty: 总在库
    - available_qty: 总可售（当前 = on_hand_qty）
    """

    on_hand_qty: Annotated[int, Field(ge=0, description="总在库数量")]
    available_qty: Annotated[int, Field(ge=0, description="总可售数量")]

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"on_hand_qty": 270, "available_qty": 270}}
    }


class ItemDetailSlice(_Base):
    """
    单条“仓 + 批次 + 数量”切片明细。

    兼容说明：
    - lot_code 为正名
    - batch_code 为兼容字段
    """

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name: Annotated[str, Field(min_length=1, max_length=100, description="仓库名称")]
    pool: Annotated[str, Field(min_length=1, max_length=32, description="库存池（MAIN / RETURNS / QUARANTINE 等，当前阶段默认 MAIN）")]

    lot_code: Optional[str] = Field(default=None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(default=None, description="批次编码（兼容字段；等价于 lot_code）")

    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日")

    on_hand_qty: Annotated[int, Field(ge=0, description="在库数量")]
    available_qty: Annotated[int, Field(ge=0, description="可售数量")]

    near_expiry: bool = Field(default=False, description="该批次是否临期（未来 30 天内到期）")
    is_top: bool = Field(default=False, description="是否属于首页历史 Top2 切片兼容字段")

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "warehouse_id": 1,
                "warehouse_name": "WH-1 MAIN",
                "pool": "MAIN",
                "lot_code": "B2025-01-A",
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


class ItemDetailDisplayResponse(_Base):
    """
    单个商品的全量“仓 + 批次”库存明细
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
                "totals": {"on_hand_qty": 270, "available_qty": 270},
                "slices": [
                    {
                        "warehouse_id": 1,
                        "warehouse_name": "WH-1 MAIN",
                        "pool": "MAIN",
                        "lot_code": "B2025-01-A",
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
    "InventoryDisplayResponse",
    "ItemDetailTotals",
    "ItemDetailSlice",
    "ItemDetailDisplayResponse",
]
