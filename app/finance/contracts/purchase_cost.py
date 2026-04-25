from __future__ import annotations

from datetime import date, datetime
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


class SkuPurchaseLedgerRow(BaseModel):
    po_line_id: int
    po_id: int
    po_no: str
    line_no: int

    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    spec_text: str | None = None

    supplier_id: int
    supplier_name: str

    purchase_time: datetime
    purchase_date: date

    qty_ordered_input: int
    purchase_uom_name_snapshot: str
    purchase_ratio_to_base_snapshot: int
    qty_ordered_base: int

    purchase_unit_price: Decimal | None = None
    planned_line_amount: Decimal
    accounting_unit_price: Decimal | None = None


class SkuPurchaseLedgerResponse(BaseModel):
    rows: list[SkuPurchaseLedgerRow]
