# app/schemas/purchase_order.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderLineListOut(BaseModel):
    id: int
    po_id: int
    line_no: int
    item_id: int

    # ✅ 后端快照：用于 PO 详情展示与契约校验（Phase M-5）
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

    qty_ordered_input: int
    purchase_ratio_to_base_snapshot: int

    qty_ordered_base: int
    qty_received_base: int
    qty_remaining_base: int

    supply_price: Optional[Decimal] = None
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_note: Optional[str] = None

    remark: Optional[str] = None

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

    close_reason: Optional[str] = None
    close_note: Optional[str] = None
    closed_by: Optional[int] = None

    canceled_at: Optional[datetime] = None
    canceled_reason: Optional[str] = None
    canceled_by: Optional[int] = None

    lines: List[PurchaseOrderLineListOut] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderWithLinesOut(BaseModel):
    """
    PO 详情输出（带行）
    Phase M-5：已移除 display-only 字符串单位字段（base_uom / uom_snapshot）
    """

    id: int
    warehouse_id: int
    warehouse_name: Optional[str] = None

    supplier_id: int
    supplier_name: str
    total_amount: Optional[Decimal] = None

    purchaser: str
    purchase_time: datetime

    remark: Optional[str] = None
    status: str

    created_at: datetime
    updated_at: datetime

    last_received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None
    close_note: Optional[str] = None
    closed_by: Optional[int] = None

    canceled_at: Optional[datetime] = None
    canceled_reason: Optional[str] = None
    canceled_by: Optional[int] = None

    lines: List[PurchaseOrderLineListOut] = []

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# V2 Create / Close inputs (required by purchase_orders_endpoints_core)
# -----------------------------------------------------------------------------


class PurchaseOrderCreateLineV2(BaseModel):
    """
    PO 创建行输入（V2）——终态合同（Phase M-5+）

    ✅ 强约束（不做兼容）：
    - 必填 uom_id + qty_input（输入单位+数量）
    - qty_base/qty_ordered_base 由服务层通过 item_uoms.ratio_to_base 推导
    """
    line_no: int
    item_id: int
    uom_id: int
    qty_input: int


class PurchaseOrderCreateV2(BaseModel):
    """
    PO 创建输入（V2）
    """
    supplier_id: int
    warehouse_id: int
    purchaser: str
    purchase_time: datetime
    remark: Optional[str] = None
    lines: List[PurchaseOrderCreateLineV2]


class PurchaseOrderCloseIn(BaseModel):
    """
    PO 人工关闭输入

    endpoints_core.py 只使用 note 字段。
    """
    note: Optional[str] = None


# -----------------------------------------------------------------------------
# Receive-line input (required by purchase_orders_endpoints_receive)
# -----------------------------------------------------------------------------


class PurchaseOrderReceiveLineIn(BaseModel):
    """
    /purchase-orders/{po_id}/receive-line 输入

    Phase M-5：
    - 支持 line_id 或 line_no 二选一（至少一个非空）
    - uom_id 为强约束（unit_governance）：若不传，后端将从 PO 行快照 purchase_uom_id_snapshot 补齐
    - 对外仍沿用 batch_code 文案（内部语义是 lot_code 展示/输入标签）
    - 日期字段可选；是否必填由商品 policy 驱动
    """
    line_id: Optional[int] = None
    line_no: Optional[int] = None

    qty: int
    uom_id: Optional[int] = None

    batch_code: Optional[str] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None
