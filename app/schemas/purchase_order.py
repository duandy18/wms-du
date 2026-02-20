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

    # ✅ 采购单价（按 base_uom 计价的单价快照）
    supply_price: Optional[Decimal] = Field(
        None, description="采购单价（按 base_uom 计价的单价快照）"
    )

    # ✅ 单位换算（方案 A）
    units_per_case: Optional[int] = Field(
        None,
        ge=1,
        description="换算因子：每 1 采购单位包含多少最小单位（>=1）。主线以 base 口径为真相",
    )

    qty_ordered: int = Field(..., gt=0, description="订购数量（按采购单位 purchase_uom）")

    # ✅ 折扣（整行减免金额 + 说明）
    discount_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="整行减免金额（>=0）。行金额不落库，按 base 口径计算",
    )
    discount_note: Optional[str] = Field(None, description="折扣说明（可选）")

    remark: Optional[str] = Field(None, description="行备注")


class PurchaseOrderLineCreate(PurchaseOrderLineBase):
    item_name: Optional[str] = Field(None, description="商品名称快照（后端生成，前端无权覆盖）")
    item_sku: Optional[str] = Field(None, description="SKU 快照（后端生成，前端无权覆盖）")
    spec_text: Optional[str] = Field(None, description="规格描述，如 1.5kg*8袋")
    base_uom: Optional[str] = Field(None, description="最小包装单位，如 袋/包/罐")
    purchase_uom: Optional[str] = Field(None, description="采购单位，如 件/箱")


class PurchaseOrderLineListOut(BaseModel):
    id: int
    po_id: int
    line_no: int
    item_id: int

    qty_ordered: int
    units_per_case: int = Field(..., ge=1, description="换算因子（>=1）")

    qty_ordered_base: int = Field(..., ge=0, description="订购数量（最小单位 base，事实字段）")

    # ✅ 已收/剩余不再来自 PO 行表列，而是由 Receipt(CONFIRMED) 聚合得到
    qty_received_base: int = Field(
        ..., ge=0, description="已收数量（最小单位 base，Receipt(CONFIRMED) 聚合）"
    )
    qty_remaining_base: int = Field(..., ge=0, description="剩余可收数量（最小单位 base，派生）")

    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None

    supply_price: Optional[Decimal] = None
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_note: Optional[str] = None

    remark: Optional[str] = None

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

    spec_text: Optional[str]
    base_uom: Optional[str]
    purchase_uom: Optional[str]

    # enrich（来自 Item / Barcode，读模型字段）
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

    # 合同字段
    supply_price: Optional[Decimal]
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_note: Optional[str] = None

    units_per_case: int = Field(..., ge=1, description="换算因子（>=1）")
    qty_ordered: int = Field(..., gt=0, description="订购数量（采购单位，展示用）")

    qty_ordered_base: int = Field(..., ge=0, description="订购数量（最小单位 base，事实字段）")

    # ✅ 执行口径（Receipt(CONFIRMED) 聚合 + 派生）
    qty_received_base: int = Field(
        ..., ge=0, description="已收数量（最小单位 base，Receipt(CONFIRMED) 聚合）"
    )
    qty_remaining_base: int = Field(..., ge=0, description="剩余可收数量（最小单位 base，派生）")

    # 展示/兼容口径（由 base + upc 换算，向下取整）
    qty_received: int = Field(..., ge=0, description="已收数量（采购单位口径，展示/兼容）")
    qty_remaining: int = Field(..., ge=0, description="剩余可收数量（采购单位口径，展示/兼容）")

    remark: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderListItemOut(BaseModel):
    id: int
    warehouse_id: int
    warehouse_name: Optional[str] = None

    supplier_id: int
    supplier_name: str
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
    warehouse_id: int

    supplier_id: int
    supplier_name: str
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
    supplier_id: int = Field(..., description="供应商 ID（必填，对应 suppliers.id）")
    warehouse_id: int = Field(..., description="仓库 ID")

    purchaser: str = Field(..., description="采购人姓名或编码")
    purchase_time: datetime = Field(..., description="采购时间（下单/确认时间）")

    remark: Optional[str] = Field(None, description="采购单备注（可选）")

    lines: List[PurchaseOrderLineCreate] = Field(
        ..., min_length=1, description="采购行列表，至少一行"
    )


class PurchaseOrderReceiveLineIn(BaseModel):
    line_id: Optional[int] = Field(None, description="行 ID（可选，优先使用）")
    line_no: Optional[int] = Field(None, description="行号（可选，line_id 缺失时用）")
    qty: int = Field(..., gt=0, description="本次收货数量（最小单位 base，>0）")

    barcode: Optional[str] = Field(
        None, description="本次收货条码（快照，写入 receipt_lines.barcode，可选）"
    )

    production_date: Optional[date] = Field(None, description="生产日期（有效期商品必填）")
    expiry_date: Optional[date] = Field(None, description="到期日期（无法推算时必填）")


# ==========================
# ✅ Phase：人工关闭采购计划
# ==========================
class PurchaseOrderCloseIn(BaseModel):
    note: Optional[str] = Field(None, description="关闭备注（可选）")
