# app/pms/items/contracts/item_uom.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ItemUomCreate(BaseModel):
    item_id: int
    uom: str = Field(..., min_length=1, max_length=16)
    ratio_to_base: int = Field(..., ge=1)
    display_name: Optional[str] = Field(None, max_length=32)
    net_weight_kg: Optional[float] = Field(None, ge=0)
    is_base: bool = False
    is_purchase_default: bool = False
    is_inbound_default: bool = False
    is_outbound_default: bool = False


class ItemUomUpdate(BaseModel):
    uom: Optional[str] = Field(None, min_length=1, max_length=16)
    ratio_to_base: Optional[int] = Field(None, ge=1)
    display_name: Optional[str] = Field(None, max_length=32)
    net_weight_kg: Optional[float] = Field(None, ge=0)
    is_base: Optional[bool] = None
    is_purchase_default: Optional[bool] = None
    is_inbound_default: Optional[bool] = None
    is_outbound_default: Optional[bool] = None


class ItemUomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    uom: str
    ratio_to_base: int
    display_name: Optional[str]
    net_weight_kg: Optional[float]
    is_base: bool
    is_purchase_default: bool
    is_inbound_default: bool
    is_outbound_default: bool


class ItemUomBarcodeRowOut(BaseModel):
    """
    owner 复合读模型：
    - 一行 = 一个商品 + 一个包装 + 零/一条码
    - 主权归 item_uoms，不归 item_barcodes
    """

    sku: str
    item_name: str

    item_id: int
    item_uom_id: int

    uom: str
    display_name: Optional[str]
    ratio_to_base: int
    net_weight_kg: Optional[float]

    is_base: bool
    is_purchase_default: bool
    is_inbound_default: bool
    is_outbound_default: bool

    barcode_id: Optional[int] = None
    barcode: Optional[str] = None
    symbology: Optional[str] = None
    is_primary: bool = False
    active: bool = False

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
