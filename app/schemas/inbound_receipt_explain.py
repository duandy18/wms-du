# app/schemas/inbound_receipt_explain.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProblemItem(BaseModel):
    """
    统一 Problem.errors 形状（前端可直接定位到 header 或 line[index]）
    """

    model_config = ConfigDict(extra="ignore")

    scope: Literal["header", "line"] = Field(..., description="错误范围：header 或 line")
    field: str = Field(..., description="对外语义字段名（不暴露内部变量名）")
    message: str = Field(..., description="错误提示（面向使用者）")
    index: Optional[int] = Field(None, description="当 scope=line 时，指向 lines 的索引")


class InboundReceiptSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    status: str
    occurred_at: Optional[datetime] = None
    warehouse_id: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    ref: Optional[str] = None
    trace_id: Optional[str] = None


class NormalizedLinePreviewOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line_key: str = Field(..., description="归一化后的行键（Phase L：LOT:<lot_id>）")
    qty_total: int = Field(..., description="归一化汇总数量")

    # Phase L：Lot 成为库存统一身份层
    # - lot_id 为 explain 层 identity 键（optional 以兼容旧前端）
    # - 不再使用 batch_code 参与分组
    lot_id: Optional[int] = Field(
        default=None,
        description="Lot ID（库存统一身份键）；Phase L 迁移期为 optional",
    )

    # 事实字段（对齐 InboundReceiptLine）
    item_id: int
    po_line_id: Optional[int] = None
    batch_code: Optional[str] = Field(
        default=None,
        description="批次码（canonical/snapshot 语义统一：有效期商品必填；非效期商品必须为 null）",
    )
    production_date: Optional[date] = None

    # 可视化/定位信息
    source_line_indexes: List[int] = Field(default_factory=list, description="来自哪些原始行 index")


class LedgerPreviewOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(..., description="动作类型（仅用于 explain 展示）")
    warehouse_id: int
    item_id: int
    qty_delta: int = Field(..., description="库存变化数量（预览）")
    source_line_key: str = Field(..., description="对应 normalized line_key")


class InboundReceiptExplainOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receipt_summary: InboundReceiptSummaryOut
    confirmable: bool = Field(..., description="是否满足确认硬校验")
    blocking_errors: List[ProblemItem] = Field(default_factory=list)
    normalized_lines_preview: List[NormalizedLinePreviewOut] = Field(default_factory=list)
    ledger_preview: List[LedgerPreviewOut] = Field(default_factory=list)
