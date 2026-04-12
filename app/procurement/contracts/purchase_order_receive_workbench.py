# app/wms/procurement/contracts/purchase_order_receive_workbench.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, AliasChoices


class PoSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_id: int
    warehouse_id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    status: Optional[str] = None
    occurred_at: Optional[datetime] = None


class ReceiptSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receipt_id: int
    ref: str
    status: str
    occurred_at: datetime


class WorkbenchBatchRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Phase L：Lot 已成为库存统一身份层
    # - lot_id 是 workbench 聚合/解释层的身份键（可选：为兼容旧前端）
    # - lot_code 仅作为展示字段，不参与 identity
    lot_id: Optional[int] = Field(
        default=None,
        description="Lot ID（库存统一身份键）；Phase L 迁移期为 optional 以兼容旧前端",
    )

    # ✅ 语义收敛：lot_code 允许为 None（表示“无批次槽位”，不是“未知展示码”）
    # - 禁止用空串/"None"/"N/A" 等伪码替代；应由后端归一化为 None
    lot_code: Optional[str] = Field(
        default=None,
        description="Lot 展示码；None 表示无批次槽位（非批次商品合法维度）",
    )
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    # ✅ 终态事实字段（base 口径）：新 worldbench 产出应优先使用 qty_base
    qty_base: int = Field(default=0, ge=0, description="收货数量（base 口径）")

    # ✅ 兼容字段：旧前端/旧测试仍使用 qty_received
    # - 输入允许来自 qty_base 或 qty_received
    # - 输出仍保留 qty_received，值与 qty_base 等价
    qty_received: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("qty_base", "qty_received"),
        description="兼容字段：等价于 qty_base（base 口径）",
    )


class WorkbenchRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_line_id: int
    line_no: int
    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

    ordered_qty: int = Field(..., description="计划数量（base 口径）")
    confirmed_received_qty: int = Field(..., description="已确认实收（base，来自 CONFIRMED receipts 聚合）")
    draft_received_qty: int = Field(..., description="草稿录入实收（base，来自当前 DRAFT receipt 聚合）")
    remaining_qty: int = Field(..., description="剩余应收（base）")

    # draft 批次聚合
    batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)

    # confirmed 批次聚合
    confirmed_batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)

    # ✅ 新增：合并批次聚合（confirmed + draft）
    all_batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)


class WorkbenchExplainOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmable: bool
    blocking_errors: List[dict] = Field(default_factory=list)
    normalized_lines_preview: List[dict] = Field(default_factory=list)


class WorkbenchCapsOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    can_confirm: bool
    can_start_draft: bool
    receipt_id: Optional[int] = None


class PurchaseOrderReceiveWorkbenchOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_summary: PoSummaryOut
    receipt: Optional[ReceiptSummaryOut] = None
    rows: List[WorkbenchRowOut]
    explain: Optional[WorkbenchExplainOut] = None
    caps: WorkbenchCapsOut
