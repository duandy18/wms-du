# app/schemas/purchase_order.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# =======================================================
# Phase 2 — 多行采购单模型（唯一形态）
# =======================================================

# ----- 行表基础字段 -----


class PurchaseOrderLineBase(BaseModel):
    line_no: int = Field(..., gt=0, description="行号，从 1 开始递增")
    item_id: int = Field(..., description="商品 ID")

    # 分组（猫条 / 双拼 / 鲜封包等）
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
        description="每件数量，仅用于金额，不进入库存",
    )

    qty_ordered: int = Field(..., gt=0, description="订购件数（按采购单位）")
    remark: Optional[str] = Field(None, description="行备注")


# ----- 创建行 -----


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


# ----- 行的返回模型 -----


class PurchaseOrderLineOut(BaseModel):
    id: int
    po_id: int
    line_no: int

    # SKU
    item_id: int
    item_name: Optional[str]
    item_sku: Optional[str]
    category: Optional[str]

    # 规格 & 单位
    spec_text: Optional[str]
    base_uom: Optional[str]
    purchase_uom: Optional[str]

    # 价格体系
    supply_price: Optional[Decimal]
    retail_price: Optional[Decimal]
    promo_price: Optional[Decimal]
    min_price: Optional[Decimal]

    # 数量体系
    qty_cases: Optional[int]
    units_per_case: Optional[int]
    qty_ordered: int
    qty_received: int

    # 金额 & 状态
    line_amount: Optional[Decimal]
    status: str
    remark: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- 带行的头表详情视图 -----


class PurchaseOrderWithLinesOut(BaseModel):
    """
    采购单详情（头 + 行）。
    头表只表达单据级别属性，数量和金额全部由行聚合。
    """

    id: int
    supplier: str
    warehouse_id: int

    # Phase 2 头表字段
    supplier_id: Optional[int]
    supplier_name: Optional[str]
    total_amount: Optional[Decimal]

    # 新增：采购人 + 采购时间
    purchaser: str
    purchase_time: datetime

    # 备注（可选）
    remark: Optional[str]

    status: str

    created_at: datetime
    updated_at: datetime
    last_received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # 行集合
    lines: List[PurchaseOrderLineOut] = []

    model_config = ConfigDict(from_attributes=True)


# ----- 创建头 + 行的请求体 -----


class PurchaseOrderCreateV2(BaseModel):
    """
    创建“头 + 多行”的请求体（唯一入口）：

    - supplier: 展示用名称
    - supplier_id: 可选，关联 suppliers.id
    - supplier_name: 可选，不传则后端用 supplier 回填
    - warehouse_id: 必填
    - purchaser: 必填，采购人
    - purchase_time: 必填，采购时间（ISO 时间）
    - remark: 整单备注（可选）
    - lines: 多行明细列表
    """

    supplier: str = Field(..., description="供应商名称（展示用）")
    warehouse_id: int = Field(..., description="仓库 ID")

    supplier_id: Optional[int] = Field(
        None,
        description="供应商 ID（可选，对应 suppliers.id）",
    )
    supplier_name: Optional[str] = Field(
        None,
        description="供应商名称快照（可选，不填则用 supplier）",
    )

    purchaser: str = Field(..., description="采购人姓名或编码")
    purchase_time: datetime = Field(..., description="采购时间（下单/确认时间）")

    remark: Optional[str] = Field(None, description="采购单备注（可选）")

    lines: List[PurchaseOrderLineCreate] = Field(
        ...,
        min_length=1,
        description="采购行列表，至少一行",
    )


class PurchaseOrderReceiveLineIn(BaseModel):
    """
    行级收货请求体（唯一收货入口）。

    - line_id / line_no 二选一，优先使用 line_id；
    - qty：本次收货件数（>0）。
    """

    line_id: Optional[int] = Field(
        None,
        description="行 ID（可选，优先使用）",
    )
    line_no: Optional[int] = Field(
        None,
        description="行号（可选，line_id 缺失时用）",
    )
    qty: int = Field(..., gt=0, description="本次收货件数（>0）")
