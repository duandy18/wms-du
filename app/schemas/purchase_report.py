# app/schemas/purchase_report.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class SupplierPurchaseReportItem(_Base):
    supplier_id: Annotated[int | None, Field(description="供应商 ID（可空）")]
    supplier_name: Annotated[
        str, Field(description="供应商名称（若 supplier_name 为空则回退 supplier）")
    ]
    order_count: Annotated[int, Field(description="采购单数量")]
    total_qty_cases: Annotated[int, Field(description="订购件数合计（件）")]
    total_units: Annotated[int, Field(description="折算最小单位数量合计")]
    total_amount: Annotated[Decimal | None, Field(description="金额合计")] = None
    avg_unit_price: Annotated[
        Decimal | None, Field(description="平均采购单价（金额 / 最小单位数）")
    ] = None


class ItemPurchaseReportItem(_Base):
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    spec_text: str | None = None

    supplier_id: int | None = None
    supplier_name: str | None = None

    order_count: int
    total_qty_cases: int
    total_units: int
    total_amount: Decimal | None = None
    avg_unit_price: Decimal | None = None


class DailyPurchaseReportItem(_Base):
    day: date
    order_count: int
    total_qty_cases: int
    total_units: int
    total_amount: Decimal | None = None
