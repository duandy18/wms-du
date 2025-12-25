# app/api/routers/channel_inventory_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BatchQtyModel(BaseModel):
    batch_code: str = Field(..., description="批次编码（包装上的批号）")
    qty: int = Field(..., description="该批次在此仓的实时库存数量")


class ChannelInventoryModel(BaseModel):
    platform: str
    shop_id: str
    warehouse_id: int
    item_id: int

    on_hand: int = Field(..., description="该仓该货品的实时库存合计（所有批次）")
    reserved_open: int = Field(..., description="该平台/店铺/仓下 open reservations 锁量")
    available: int = Field(..., description="可售量 = max(on_hand - reserved_open, 0)")

    batches: List[BatchQtyModel] = Field(
        default_factory=list,
        description="按批次的库存明细（仅供人工参考，不影响 available 口径）",
    )


class WarehouseInventoryModel(BaseModel):
    warehouse_id: int
    on_hand: int
    reserved_open: int
    available: int
    batches: List[BatchQtyModel] = Field(default_factory=list)

    is_top: bool = Field(False, description="是否主仓（store_warehouse.is_top）")
    is_default: bool = Field(False, description="是否默认仓（历史字段）")
    priority: int = Field(100, description="路由优先级（数字越小越优先）")


class ChannelInventoryMultiModel(BaseModel):
    platform: str
    shop_id: str
    item_id: int
    warehouses: List[WarehouseInventoryModel] = Field(
        default_factory=list, description="各仓的库存与锁量明细"
    )
