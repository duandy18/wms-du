from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class OrderSalesSummary(BaseModel):
    order_count: int
    line_count: int
    qty_sold: int
    revenue: Decimal
    avg_order_value: Decimal | None = None
    median_order_value: Decimal | None = None


class OrderSalesDailyRow(BaseModel):
    day: date
    order_count: int
    line_count: int
    qty_sold: int
    revenue: Decimal


class OrderSalesStoreRow(BaseModel):
    platform: str
    store_code: str
    store_name: str | None = None
    order_count: int
    line_count: int
    qty_sold: int
    revenue: Decimal


class OrderSalesItemRow(BaseModel):
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    sku_id: str | None = None
    title: str | None = None
    qty_sold: int
    revenue: Decimal


class OrderSalesLineRow(BaseModel):
    id: int
    order_id: int
    order_item_id: int

    platform: str
    store_id: int
    store_code: str
    store_name: str | None = None

    ext_order_no: str
    order_ref: str
    order_status: str | None = None
    order_created_at: datetime
    order_date: date

    receiver_province: str | None = None
    receiver_city: str | None = None
    receiver_district: str | None = None

    warehouse_id: int | None = None
    warehouse_name: str | None = None
    warehouse_source: str

    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    sku_id: str | None = None
    title: str | None = None

    qty_sold: int
    unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    line_amount: Decimal

    order_amount: Decimal | None = None
    pay_amount: Decimal | None = None


class OrderSalesResponse(BaseModel):
    summary: OrderSalesSummary
    daily: list[OrderSalesDailyRow]
    by_store: list[OrderSalesStoreRow]
    by_item: list[OrderSalesItemRow]
    items: list[OrderSalesLineRow]
    total: int
    limit: int
    offset: int
