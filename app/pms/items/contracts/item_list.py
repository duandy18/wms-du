# app/pms/items/contracts/item_list.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ItemListRowOut(BaseModel):
    """
    PMS 商品列表页专用 owner 读模型。

    定位：
    - 一行 = 一个商品的完整列表摘要
    - 只服务商品主数据总览页
    - 不承载写入语义
    - 不让前端再自行拼 item_uoms / item_barcodes / item_sku_codes / item_attribute_values
    """

    item_id: int
    sku: str
    name: str
    spec: Optional[str] = None
    enabled: bool

    brand: Optional[str] = None
    category: Optional[str] = None
    supplier_name: Optional[str] = None

    primary_barcode: Optional[str] = None

    base_uom: Optional[str] = None
    base_net_weight_kg: Optional[float] = Field(default=None, ge=0)

    purchase_uom: Optional[str] = None
    purchase_ratio_to_base: Optional[int] = Field(default=None, ge=1)

    lot_source_policy: str
    expiry_policy: str
    shelf_life_value: Optional[int] = Field(default=None, ge=0)
    shelf_life_unit: Optional[str] = None

    uom_count: int = Field(default=0, ge=0)
    barcode_count: int = Field(default=0, ge=0)
    sku_code_count: int = Field(default=0, ge=0)
    attribute_count: int = Field(default=0, ge=0)

    updated_at: Optional[datetime] = None
