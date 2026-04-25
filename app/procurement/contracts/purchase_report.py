# app/procurement/contracts/purchase_report.py
from __future__ import annotations

from datetime import date, datetime
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
    supplier_name: Annotated[str, Field(description="供应商名称（快照/展示用）")]
    order_count: Annotated[int, Field(description="采购单数量")]
    total_qty_cases: Annotated[int, Field(description="订购件数合计（件，辅助展示口径）")]
    total_units: Annotated[int, Field(description="折算最小单位数量合计")]
    total_amount: Annotated[Decimal | None, Field(description="计划金额合计")] = None
    avg_unit_price: Annotated[
        Decimal | None, Field(description="平均采购单价（计划金额 / 最小单位数）")
    ] = None


class ItemPurchaseReportItem(_Base):
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None

    # 保留后端返回能力，前端底表是否展示由页面决定
    barcode: str | None = Field(default=None, description="主条码（来自 item_barcodes 主条码）")
    brand: str | None = Field(default=None, description="品牌（来自 items.brand）")
    category: str | None = Field(default=None, description="分类（来自 items.category）")

    spec_text: str | None = None

    # 按商品聚合时默认不再带供应商语义；仅当显式按 supplier 过滤时，回显当前过滤供应商
    supplier_id: int | None = None
    supplier_name: str | None = None

    order_count: int
    total_qty_cases: int
    total_units: int
    total_amount: Decimal | None = None
    avg_unit_price: Decimal | None = None


class ItemPurchaseReportLineItem(_Base):
    po_id: int
    po_no: str
    po_line_id: int
    line_no: int

    warehouse_id: int
    supplier_id: int
    supplier_name: str

    purchase_time: datetime
    purchase_uom_name_snapshot: str

    qty_ordered_input: int
    qty_ordered_base: int

    supply_price_snapshot: Decimal | None = None
    planned_line_amount: Decimal


class DailyPurchaseReportItem(_Base):
    day: date
    order_count: int
    total_qty_cases: int
    total_units: int
    total_amount: Decimal | None = None


class SummaryPurchaseReportItem(_Base):
    order_count: Annotated[int, Field(description="采购单数量")]
    supplier_count: Annotated[int, Field(description="供应商数量")]
    item_count: Annotated[int, Field(description="商品数量")]
    total_qty_cases: Annotated[int, Field(description="订购件数合计（件，辅助展示口径）")]
    total_units: Annotated[int, Field(description="折算最小单位数量合计")]
    total_amount: Annotated[Decimal, Field(description="计划金额合计")]
    avg_unit_price: Annotated[
        Decimal | None, Field(description="平均采购单价（计划金额 / 最小单位数）")
    ] = None
