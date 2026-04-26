# app/shipping_assist/reports/contracts.py
#
# 分拆说明：
# - 本文件承载 TMS / Reports（运输报表）相关合同；
# - 当前报表口径统一基于 shipping_records（物流台帐）；
# - Reports 域只保留聚合分析与筛选项。
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ShippingByCarrierRow(BaseModel):
    shipping_provider_code: Optional[str] = None
    shipping_provider_name: Optional[str] = None
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


class ShippingByStoreRow(BaseModel):
    platform: str
    store_code: str
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByStoreResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByStoreRow]


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


class ShippingReportFilterOptions(BaseModel):
    platforms: List[str]
    store_codes: List[str]
    provinces: List[str]
    cities: List[str]
