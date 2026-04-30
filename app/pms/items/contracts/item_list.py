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


class ItemListUomOut(BaseModel):
    id: int
    item_id: int
    uom: str
    display_name: Optional[str] = None
    ratio_to_base: int = Field(ge=1)
    net_weight_kg: Optional[float] = Field(default=None, ge=0)
    is_base: bool
    is_purchase_default: bool
    is_inbound_default: bool
    is_outbound_default: bool
    updated_at: Optional[datetime] = None


class ItemListBarcodeOut(BaseModel):
    id: int
    item_id: int
    item_uom_id: int
    uom: Optional[str] = None
    display_name: Optional[str] = None
    barcode: str
    symbology: str
    active: bool
    is_primary: bool
    updated_at: Optional[datetime] = None


class ItemListSkuCodeOut(BaseModel):
    id: int
    item_id: int
    code: str
    code_type: str
    is_primary: bool
    is_active: bool
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    remark: Optional[str] = None
    updated_at: Optional[datetime] = None


class ItemListAttributeOut(BaseModel):
    attribute_def_id: int
    code: str
    name_cn: str
    value_type: str
    selection_mode: str
    unit: Optional[str] = None
    is_item_required: bool
    is_sku_required: bool
    is_sku_segment: bool
    sort_order: int

    value_text: Optional[str] = None
    value_number: Optional[float] = None
    value_bool: Optional[bool] = None
    value_option_ids: list[int] = Field(default_factory=list)
    value_option_code_snapshots: list[str] = Field(default_factory=list)
    value_option_names: list[str] = Field(default_factory=list)
    value_unit_snapshot: Optional[str] = None
    updated_at: Optional[datetime] = None


class ItemListDetailOut(BaseModel):
    """
    PMS 商品列表详情读模型。

    定位：
    - 只读展示合同
    - 给商品列表页“详情展开”使用
    - row 复用 ItemListRowOut，确保列表摘要与详情头部一致
    """

    row: ItemListRowOut
    uoms: list[ItemListUomOut]
    barcodes: list[ItemListBarcodeOut]
    sku_codes: list[ItemListSkuCodeOut]
    attributes: list[ItemListAttributeOut]
