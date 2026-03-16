# app/tms/reports/contracts.py
#
# 分拆说明：
# - 本文件承载 TMS / Reports（运输报表）相关合同；
# - 当前报表口径统一基于 shipping_records（物流台帐）；
# - list 明细会额外左连 shipping_record_reconciliations（差异处理表）。
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ShippingByCarrierRow(BaseModel):
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByCarrierResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByCarrierRow]


class ShippingByProvinceRow(BaseModel):
    province: Optional[str] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByProvinceResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByProvinceRow]


class ShippingByShopRow(BaseModel):
    platform: str
    shop_id: str
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByShopResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByShopRow]


class ShippingByWarehouseRow(BaseModel):
    warehouse_id: Optional[int] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByWarehouseResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByWarehouseRow]


class ShippingDailyRow(BaseModel):
    stat_date: str
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingDailyResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingDailyRow]


class ShippingListRow(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str
    warehouse_id: Optional[int] = None

    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None

    gross_weight_kg: Optional[float] = None
    cost_estimated: Optional[float] = None

    dest_province: Optional[str] = None
    dest_city: Optional[str] = None

    has_diff: bool
    carrier_bill_item_id: Optional[int] = None
    weight_diff_kg: Optional[float] = None
    cost_diff: Optional[float] = None
    adjust_amount: Optional[float] = None

    created_at: str


class ShippingListResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingListRow]
    total: int


class ShippingReportFilterOptions(BaseModel):
    platforms: List[str]
    shop_ids: List[str]
    provinces: List[str]
    cities: List[str]
