from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PurchaseCostSummary(BaseModel):
    purchase_order_count: int
    supplier_count: int
    item_count: int
    purchase_amount: Decimal
    avg_unit_cost: Decimal | None = None


class PurchaseCostDailyRow(BaseModel):
    day: date
    purchase_order_count: int
    purchase_amount: Decimal


class PurchaseCostSupplierRow(BaseModel):
    supplier_id: int | None = None
    supplier_name: str
    purchase_order_count: int
    purchase_amount: Decimal
    avg_unit_cost: Decimal | None = None


class PurchaseCostItemRow(BaseModel):
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    total_units: int
    purchase_amount: Decimal
    avg_unit_cost: Decimal | None = None


class PurchaseCostResponse(BaseModel):
    summary: PurchaseCostSummary
    daily: list[PurchaseCostDailyRow]
    by_supplier: list[PurchaseCostSupplierRow]
    by_item: list[PurchaseCostItemRow]
