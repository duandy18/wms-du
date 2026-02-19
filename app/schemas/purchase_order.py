# app/schemas/purchase_order.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# =======================================================
# Phase 2 — 多行采购单模型（唯一形态）
# =======================================================


class PurchaseOrderLineBase(BaseModel):
    line_no: int = Field(..., gt=0, description="行号，从 1 开始递增")
    item_id: int = Field(..., description="商品 ID")

    category: Optional[str] = Field(
        None,
        description="业务分组，如 猫条/双拼/鲜封包（当前前端不编辑，保留兼容）",
    )

    supply_price: Optional[Decimal] = Field(None, description="供货价")
    retail_price: Optional[Decimal] = Field(None, description="零售价")
    promo_price: Optional[Decimal] = Field(None, description="活动后单价")
    min_price: Optional[Decimal] = Field(None, description="厂家控制价/最低价")

    qty_cases: Optional[int] = Field(None, ge=0, description="件数（箱数），库存单位仍为件")
    units_per_case: Optional[int] = Field(None, ge=0, description="每件数量（换算因子）；主线以 base 口径为真相")

    qty_ordered: int = Field(..., gt=0, description="订购数量（按采购单位 purchase_uom）")
    remark: Optional[str] = Field(None, description="行备注")


class PurchaseOrderLineCreate(PurchaseOrderLineBase):
    item_name: Optional[str] = Field(None, description="商品名称快照")
    item_sku: Optional[str] = Field(None, description="SKU 快照")
    spec_text: Optional[str] = Field(None, description="规格描述，如 1.5kg*8袋")
    base_uom: Optional[str] = Field(None, description="最小包装单位，如 袋/包/罐")
    purchase_uom: Optional[str] = Field(None, description="采购单位，如 件/箱")


class PurchaseOrderLineListOut(BaseModel):
    id: int
    po_id: int
    line_no: int
    item_id: int

    qty_ordered: int

    qty_ordered_base: int
    qty_received_base: int = Field(..., ge=0, description="最小单位已收数量（事实字段）")

    status: str

    units_per_case: Optional[int] = None
    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderLineOut(BaseModel):
    id: int
    po_id: int
    line_no: int

    item_id: int
    item_name: Optional[str]
    item_sku: Optional[str]

    biz_category: Optional[str] = Field(None, description="PO 行业务分组快照（兼容旧 category）")

    spec_text: Optional[str]
    base_uom: Optional[str]
    purchase_uom: Optional[str]

    sku: Optional[str] = None
    primary_barcode: Optional[str] = None

    brand: Optional[str] = None
    category: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    uom: Optional[str] = None

    has_shelf_life: Optional[bool] = None
    shelf_life_value: Optional[int] = None
    shelf_life_unit: Optional[str] = None
    enabled: Optional[bool] = None

    supply_price: Optional[Decimal]
    retail_price: Optional[Decimal]
    promo_price: Optional[Decimal]
    min_price: Optional[Decimal]

    qty_cases: Optional[int]
    units_per_case: Optional[int]
    qty_ordered: int = Field(..., gt=0, description="订购数量（采购单位，展示用）")

    qty_ordered_base: int = Field(..., gt=0, description="订购数量（最小单位 base，事实字段）")
    qty_received_base: int = Field(..., ge=0, description="已收数量（最小单位 base，事实字段）")
    qty_remaining_base: int = Field(..., ge=0, description="剩余可收数量（最小单位 base，事实字段）")

    qty_received: int = Field(..., ge=0, description="已收数量（采购单位口径，展示/兼容）")
    qty_remaining: int = Field(..., ge=0, description="剩余可收数量（采购单位口径，展示/兼容）")

    line_amount: Optional[Decimal]
    status: str
    remark: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderListItemOut(BaseModel):
    id: int
    supplier: str
    warehouse_id: int
    warehouse_name: Optional[str] = None

    supplier_id: Optional[int]
    supplier_name: Optional[str]
    total_amount: Optional[Decimal]

    purchaser: str
    purchase_time: datetime

    remark: Optional[str]
    status: str

    created_at: datetime
    updated_at: datetime
    last_received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # ✅ 关闭审计
    close_reason: Optional[str] = None
    close_note: Optional[str] = None
    closed_by: Optional[int] = None

    # ✅ 取消审计（预留）
    canceled_at: Optional[datetime] = None
    canceled_reason: Optional[str] = None
    canceled_by: Optional[int] = None

    lines: List[PurchaseOrderLineListOut] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderWithLinesOut(BaseModel):
    id: int
    supplier: str
    warehouse_id: int

    supplier_id: Optional[int]
    supplier_name: Optional[str]
    total_amount: Optional[Decimal]

    purchaser: str
    purchase_time: datetime

    remark: Optional[str]
    status: str

    created_at: datetime
    updated_at: datetime
    last_received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # ✅ 关闭审计
    close_reason: Optional[str] = None
    close_note: Optional[str] = None
    closed_by: Optional[int] = None

    canceled_at: Optional[datetime] = None
    canceled_reason: Optional[str] = None
    canceled_by: Optional[int] = None

    lines: List[PurchaseOrderLineOut] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCreateV2(BaseModel):
    supplier: str = Field(..., description="供应商名称（展示用）")
    warehouse_id: int = Field(..., description="仓库 ID")

    supplier_id: Optional[int] = Field(None, description="供应商 ID（可选，对应 suppliers.id）")
    supplier_name: Optional[str] = Field(None, description="供应商名称快照（可选，不填则用 supplier）")

    purchaser: str = Field(..., description="采购人姓名或编码")
    purchase_time: datetime = Field(..., description="采购时间（下单/确认时间）")

    remark: Optional[str] = Field(None, description="采购单备注（可选）")

    lines: List[PurchaseOrderLineCreate] = Field(..., min_length=1, description="采购行列表，至少一行")


class PurchaseOrderReceiveLineIn(BaseModel):
    line_id: Optional[int] = Field(None, description="行 ID（可选，优先使用）")
    line_no: Optional[int] = Field(None, description="行号（可选，line_id 缺失时用）")
    qty: int = Field(..., gt=0, description="本次收货数量（最小单位 base，>0）")

    barcode: Optional[str] = Field(None, description="本次收货条码（快照，写入 receipt_lines.barcode，可选）")

    production_date: Optional[date] = Field(None, description="生产日期（有效期商品必填）")
    expiry_date: Optional[date] = Field(None, description="到期日期（无法推算时必填）")


# ==========================
# ✅ Phase：人工关闭采购计划
# ==========================
class PurchaseOrderCloseIn(BaseModel):
    note: Optional[str] = Field(None, description="关闭备注（可选）")
