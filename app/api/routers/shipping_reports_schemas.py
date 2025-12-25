# app/api/routers/shipping_reports_schemas.py
from __future__ import annotations

from typing import Any, List, Optional

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
    stat_date: str  # YYYY-MM-DD
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

    trace_id: Optional[str] = None

    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None

    gross_weight_kg: Optional[float] = None
    packaging_weight_kg: Optional[float] = None
    cost_estimated: Optional[float] = None

    status: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
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
