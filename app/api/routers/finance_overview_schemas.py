# app/api/routers/finance_overview_schemas.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class FinanceDailyRow(BaseModel):
    day: date
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    fulfillment_ratio: Optional[Decimal] = None


class FinanceShopRow(BaseModel):
    platform: str
    shop_id: str
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    fulfillment_ratio: Optional[Decimal] = None


class FinanceSkuRow(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_sold: int
    revenue: Decimal
    purchase_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None


class OrderUnitSummary(BaseModel):
    order_count: int
    revenue: Decimal
    avg_order_value: Optional[Decimal] = None
    median_order_value: Optional[Decimal] = None


class OrderUnitContributionPoint(BaseModel):
    percent_orders: float  # 0~1
    percent_revenue: float  # 0~1


class OrderUnitRow(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    order_value: Decimal
    created_at: str  # ISO 字符串
