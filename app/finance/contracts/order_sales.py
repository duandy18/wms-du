from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class OrderSalesSummary(BaseModel):
    order_count: int
    revenue: Decimal
    avg_order_value: Decimal | None = None
    median_order_value: Decimal | None = None


class OrderSalesDailyRow(BaseModel):
    day: date
    order_count: int
    revenue: Decimal


class OrderSalesShopRow(BaseModel):
    platform: str
    shop_id: str
    order_count: int
    revenue: Decimal


class OrderSalesItemRow(BaseModel):
    item_id: int
    sku_id: str | None = None
    title: str | None = None
    qty_sold: int
    revenue: Decimal


class OrderSalesTopOrderRow(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    order_value: Decimal
    created_at: datetime


class OrderSalesResponse(BaseModel):
    summary: OrderSalesSummary
    daily: list[OrderSalesDailyRow]
    by_shop: list[OrderSalesShopRow]
    by_item: list[OrderSalesItemRow]
    top_orders: list[OrderSalesTopOrderRow]
