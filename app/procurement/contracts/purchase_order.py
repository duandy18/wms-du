# app/procurement/contracts/purchase_order.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseOrderLineListOut(BaseModel):
    id: int
    po_id: int
    line_no: int
    item_id: int

    # ✅ 后端快照：用于 PO 详情展示与契约校验（Phase M-5）
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    spec_text: Optional[str] = None

    purchase_uom_id_snapshot: int
    qty_ordered_input: int
    purchase_ratio_to_base_snapshot: int
    qty_ordered_base: int

    supply_price: Optional[Decimal] = None
    remark: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderListItemOut(BaseModel):
    id: int
    po_no: str
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
    po_no: str
    warehouse_id: int
    warehouse_name: Optional[str] = None

    supplier_id: int
    supplier_name: str
    total_amount: Optional[Decimal] = None

    purchaser: str
    purchase_time: datetime

    remark: Optional[str] = None
    status: str
    editable: bool = False
    edit_block_reason: Optional[str] = None

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
# V2 Create / Update / Close inputs
# -----------------------------------------------------------------------------


class PurchaseOrderCreateLineV2(BaseModel):
    """
    PO 创建行输入（V2）——终态合同

    严格合同：
    - 必填：line_no / item_id / uom_id / qty_input
    - 可选商业字段：supply_price / remark
    - 快照与派生字段（item_name / ratio_to_base / qty_ordered_base）不允许前端直传
    """

    line_no: int = Field(gt=0)
    item_id: int = Field(gt=0)
    uom_id: int = Field(gt=0)
    qty_input: int = Field(gt=0)

    supply_price: Optional[Decimal] = Field(default=None, ge=0)
    remark: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("remark")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class PurchaseOrderCreateV2(BaseModel):
    """
    PO 创建输入（V2）
    """

    supplier_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    purchaser: str
    purchase_time: datetime
    remark: Optional[str] = None
    lines: List[PurchaseOrderCreateLineV2] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("purchaser")
    @classmethod
    def _validate_purchaser(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("purchaser 不能为空")
        return s

    @field_validator("remark")
    @classmethod
    def _normalize_remark(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class PurchaseOrderUpdateLineV2(PurchaseOrderCreateLineV2):
    """
    PO 更新行输入（V2）——严格 full replace 合同
    """


class PurchaseOrderUpdateV2(PurchaseOrderCreateV2):
    """
    PO 更新输入（V2）——严格 full replace 合同
    """


class PurchaseOrderCloseIn(BaseModel):
    """
    PO 人工关闭输入

    endpoints_core.py 只使用 note 字段。
    """

    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def _normalize_note(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 历史 receive-line 合同（兼容期保留）
# -----------------------------------------------------------------------------


class PurchaseOrderReceiveLineIn(BaseModel):
    """
    /purchase-orders/{po_id}/receive-line 输入

    Phase M-5：
    - 支持 line_id 或 line_no 二选一（至少一个非空）
    - uom_id 为强约束（unit_governance）：若不传，后端将从 PO 行快照 purchase_uom_id_snapshot 补齐
    - 输入字段统一为 lot_code
    - 日期字段可选；是否必填由商品 policy 驱动
    """

    line_id: Optional[int] = None
    line_no: Optional[int] = None

    qty: int
    uom_id: Optional[int] = None

    lot_code: Optional[str] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None
