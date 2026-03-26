# app/tms/shipment/contracts_prepare_orders.py
# 分拆说明：
# - 本文件从 contracts_prepare.py 中拆出“发运准备-订单与地址”相关合同。
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ShipPrepareImportRequest(BaseModel):
    platform: str = Field(..., description="平台，例如 PDD")
    shop_id: str = Field(..., description="店铺 ID，例如 '1'")
    ext_order_no: str = Field(..., description="平台订单号")
    address_ready_status: str = Field(..., description="OMS 地址状态：pending / ready")


class ShipPrepareImportResponse(BaseModel):
    ok: bool = True
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    address_ready_status: str


class ShipPrepareOrdersListItemOut(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None

    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None

    address_summary: str


class ShipPrepareOrdersListResponse(BaseModel):
    ok: bool = True
    items: List[ShipPrepareOrdersListItemOut] = Field(default_factory=list)


class ShipPrepareOrderDetailOut(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None

    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None

    address_summary: str
    address_ready_status: str


class ShipPrepareOrderDetailResponse(BaseModel):
    ok: bool = True
    item: ShipPrepareOrderDetailOut


class ShipPrepareAddressConfirmRequest(BaseModel):
    address_ready_status: str = Field(..., description="当前仅支持 ready")


class ShipPrepareAddressConfirmResponse(BaseModel):
    ok: bool = True
    item: ShipPrepareOrderDetailOut
