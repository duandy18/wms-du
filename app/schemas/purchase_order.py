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

    # 分组（猫条 / 双拼 / 鲜封包等）——这是 PO 行自己的业务分组快照，不等于 Item 主数据的“品类”
    category: Optional[str] = Field(
        None,
        description="业务分组，如 猫条/双拼/鲜封包（当前前端不编辑，保留兼容）",
    )

    # 价格体系
    supply_price: Optional[Decimal] = Field(None, description="供货价")
    retail_price: Optional[Decimal] = Field(None, description="零售价")
    promo_price: Optional[Decimal] = Field(None, description="活动后单价")
    min_price: Optional[Decimal] = Field(None, description="厂家控制价/最低价")

    # 数量体系
    qty_cases: Optional[int] = Field(
        None,
        ge=0,
        description="件数（箱数），库存单位仍为件",
    )
    units_per_case: Optional[int] = Field(
        None,
        ge=0,
        description="每件数量（换算因子）；库存/核算主线以 base 口径为真相",
    )

    qty_ordered: int = Field(..., gt=0, description="订购数量（按采购单位 purchase_uom）")
    remark: Optional[str] = Field(None, description="行备注")


class PurchaseOrderLineCreate(PurchaseOrderLineBase):
    """
    创建行时可带商品快照信息和规格视图：
    - item_name: 商品名称快照
    - item_sku: SKU 快照
    - spec_text: 规格描述，如 1.5kg*8袋
    - base_uom: 最小单位，如 袋/包/罐
    - purchase_uom: 采购单位，如 件/箱
    """

    item_name: Optional[str] = Field(None, description="商品名称快照")
    item_sku: Optional[str] = Field(None, description="SKU 快照")
    spec_text: Optional[str] = Field(None, description="规格描述，如 1.5kg*8袋")
    base_uom: Optional[str] = Field(None, description="最小包装单位，如 袋/包/罐")
    purchase_uom: Optional[str] = Field(None, description="采购单位，如 件/箱")


# -----------------------
# ✅ 列表态：轻量行输出（不含 qty_remaining，不做主数据补齐）
# -----------------------
class PurchaseOrderLineListOut(BaseModel):
    """
    列表态行输出：只保证行自身的最小字段，避免“详情态强合同字段”污染列表接口。

    ✅ Phase B 收敛补充（关键）：
    - 列表态也显性化 base 口径字段（唯一真相），避免前端自行推导：
        * qty_ordered_base
        * qty_received_base
      remaining 若需要，由详情态提供（避免列表接口合同膨胀）
    - units_per_case/base_uom/purchase_uom 用于展示换算解释
    """
    id: int
    po_id: int
    line_no: int
    item_id: int

    # 展示口径（采购单位）
    qty_ordered: int

    # ✅ base 口径（唯一真相）
    qty_ordered_base: int  # 最小单位订购量（事实字段）
    qty_received_base: int = Field(..., ge=0, description="最小单位已收数量（事实字段）")

    # 兼容字段：历史上这里叫 qty_received，但语义容易误解；列表态保留 status 用于展示
    status: str

    # ✅ 最小单位换算与单位快照（列表态也要有，便于统一口径展示）
    units_per_case: Optional[int] = None
    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------
# ✅ 详情态：强合同行输出（含 remaining + 主数据补齐）
# -----------------------
class PurchaseOrderLineOut(BaseModel):
    id: int
    po_id: int
    line_no: int

    # ====== PO 行快照（历史兼容）======
    item_id: int
    item_name: Optional[str]
    item_sku: Optional[str]

    # ⚠️ PO 行的业务分组快照（不等于 Item 主数据的品类）
    biz_category: Optional[str] = Field(None, description="PO 行业务分组快照（兼容旧 category）")

    # 规格 & 单位（PO 行快照）
    spec_text: Optional[str]
    base_uom: Optional[str]
    purchase_uom: Optional[str]

    # ====== Item 主数据字段（用于与商品主数据列完全对齐）======
    sku: Optional[str] = None
    primary_barcode: Optional[str] = None

    brand: Optional[str] = None
    category: Optional[str] = None  # Item 主数据“品类”
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    uom: Optional[str] = None

    has_shelf_life: Optional[bool] = None
    shelf_life_value: Optional[int] = None
    shelf_life_unit: Optional[str] = None
    enabled: Optional[bool] = None

    # 价格体系
    supply_price: Optional[Decimal]
    retail_price: Optional[Decimal]
    promo_price: Optional[Decimal]
    min_price: Optional[Decimal]

    # 数量体系（展示字段：采购单位）
    qty_cases: Optional[int]
    units_per_case: Optional[int]
    qty_ordered: int = Field(..., gt=0, description="订购数量（采购单位 purchase_uom，展示用）")

    # ✅ base 口径（唯一真相）
    qty_ordered_base: int = Field(..., gt=0, description="订购数量（最小单位 base，事实字段）")
    qty_received_base: int = Field(..., ge=0, description="已收数量（最小单位 base，事实字段）")
    qty_remaining_base: int = Field(..., ge=0, description="剩余可收数量（最小单位 base，事实字段）")

    # 兼容字段（采购单位口径，仅展示/历史兼容）
    qty_received: int = Field(
        ...,
        ge=0,
        description="已收数量（采购单位口径，展示/兼容字段；判断逻辑请使用 qty_received_base）",
    )
    qty_remaining: int = Field(
        ...,
        ge=0,
        description="剩余可收数量（采购单位口径，展示/兼容字段；判断逻辑请使用 qty_remaining_base）",
    )

    # 金额 & 状态
    line_amount: Optional[Decimal]
    status: str
    remark: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------
# ✅ 列表态：采购单列表输出
# -----------------------
class PurchaseOrderListItemOut(BaseModel):
    """
    列表态采购单：用于 /purchase-orders/ 列表。
    - 不做主数据补齐
    - 行使用 PurchaseOrderLineListOut（无 qty_remaining）
    """
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

    lines: List[PurchaseOrderLineListOut] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderWithLinesOut(BaseModel):
    """
    采购单详情（头 + 行，强合同）。

    ✅ 合同收敛（关键）：
    - “是否可继续收货 / 是否允许新建收货任务”只能看 base 口径：
        sum(lines.qty_remaining_base) > 0
    - 前端不得自行推导 base remaining（避免第二真相）
    """
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

    lines: List[PurchaseOrderLineOut] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCreateV2(BaseModel):
    """
    创建“头 + 多行”的请求体（唯一入口）
    """
    supplier: str = Field(..., description="供应商名称（展示用）")
    warehouse_id: int = Field(..., description="仓库 ID")

    supplier_id: Optional[int] = Field(None, description="供应商 ID（可选，对应 suppliers.id）")
    supplier_name: Optional[str] = Field(None, description="供应商名称快照（可选，不填则用 supplier）")

    purchaser: str = Field(..., description="采购人姓名或编码")
    purchase_time: datetime = Field(..., description="采购时间（下单/确认时间）")

    remark: Optional[str] = Field(None, description="采购单备注（可选）")

    lines: List[PurchaseOrderLineCreate] = Field(..., min_length=1, description="采购行列表，至少一行")


class PurchaseOrderReceiveLineIn(BaseModel):
    """
    行级收货请求体（唯一收货入口）。
    """
    line_id: Optional[int] = Field(None, description="行 ID（可选，优先使用）")
    line_no: Optional[int] = Field(None, description="行号（可选，line_id 缺失时用）")
    qty: int = Field(..., gt=0, description="本次收货数量（最小单位 base，>0）")

    barcode: Optional[str] = Field(None, description="本次收货条码（快照，写入 receipt_lines.barcode，可选）")

    production_date: Optional[date] = Field(None, description="生产日期（有效期商品必填）")
    expiry_date: Optional[date] = Field(None, description="到期日期（无法推算时必填）")
