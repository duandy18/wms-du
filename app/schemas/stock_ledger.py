# app/schemas/stock_ledger.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    """
    通用基类：
    - from_attributes: 支持 SQLAlchemy ORM 自动序列化
    - extra = ignore: 兼容老字段
    - populate_by_name: 支持 alias
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# =========================================================
# 冻结枚举（OpenAPI 唯一真源）
# =========================================================
class ReasonCanon(str, Enum):
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    ADJUSTMENT = "ADJUSTMENT"


class SubReason(str, Enum):
    PO_RECEIPT = "PO_RECEIPT"
    ORDER_SHIP = "ORDER_SHIP"
    COUNT_ADJUST = "COUNT_ADJUST"
    RETURN_RECEIPT = "RETURN_RECEIPT"
    INTERNAL_SHIP = "INTERNAL_SHIP"
    RETURN_TO_VENDOR = "RETURN_TO_VENDOR"


# =========================================================
# 查询入参（明细 / 统计 / 对账 / 历史 共用）
# =========================================================
class LedgerQuery(_Base):
    """
    库存台账查询条件（统一合同）：
    """

    item_id: Optional[int] = Field(default=None, description="商品 ID（精确）")
    item_keyword: Optional[str] = Field(default=None, description="商品关键词（模糊匹配 name / sku）")
    warehouse_id: Optional[int] = Field(default=None, description="仓库 ID")
    batch_code: Optional[str] = Field(default=None, max_length=64, description="批次编码（精确）")

    reason: Optional[str] = Field(
        default=None,
        max_length=32,
        description="原始 reason（如 OUTBOUND_SHIP / RECEIPT / ADJUSTMENT）",
    )

    reason_canon: Optional[ReasonCanon] = Field(
        default=None,
        description="稳定口径（RECEIPT / SHIPMENT / ADJUSTMENT）",
    )
    sub_reason: Optional[SubReason] = Field(
        default=None,
        description="具体动作（PO_RECEIPT / ORDER_SHIP / COUNT_ADJUST 等）",
    )

    ref: Optional[str] = Field(default=None, max_length=128, description="关联单据（精确匹配）")
    trace_id: Optional[str] = Field(default=None, max_length=64, description="追溯号 trace_id（精确匹配）")

    time_from: Optional[datetime] = Field(default=None, description="开始时间（含，基于 occurred_at）")
    time_to: Optional[datetime] = Field(default=None, description="结束时间（含，基于 occurred_at）")

    limit: Annotated[int, Field(ge=1, le=1000)] = 100
    offset: Annotated[int, Field(ge=0)] = 0

    @field_validator(
        "item_keyword",
        "batch_code",
        "reason",
        "ref",
        "trace_id",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v


# =========================================================
# 单条台账记录（返回行）
# =========================================================
class LedgerRow(_Base):
    id: int
    delta: int
    after_qty: int

    reason: str
    reason_canon: Optional[str] = None
    sub_reason: Optional[str] = None

    ref: Optional[str] = None
    ref_line: int

    occurred_at: datetime
    created_at: datetime

    warehouse_id: int
    item_id: int
    item_name: Optional[str] = None
    batch_code: str

    trace_id: Optional[str] = None
    movement_type: Optional[str] = None


class LedgerList(_Base):
    total: int
    items: List[LedgerRow] = Field(default_factory=list)


class LedgerEnums(_Base):
    reason_canons: List[ReasonCanon] = Field(default_factory=list)
    sub_reasons: List[SubReason] = Field(default_factory=list)


# =========================================================
# 统计 / 对账
# =========================================================
class LedgerReasonStat(_Base):
    reason: str
    count: int
    total_delta: int


class LedgerSummary(_Base):
    filters: LedgerQuery
    by_reason: List[LedgerReasonStat] = Field(default_factory=list)
    net_delta: int


class LedgerReconcileRow(_Base):
    warehouse_id: int
    item_id: int
    batch_code: str
    ledger_sum_delta: int
    stock_qty: int
    diff: int


class LedgerReconcileResult(_Base):
    rows: List[LedgerReconcileRow] = Field(default_factory=list)


__all__ = [
    "ReasonCanon",
    "SubReason",
    "LedgerEnums",
    "LedgerQuery",
    "LedgerRow",
    "LedgerList",
    "LedgerReasonStat",
    "LedgerSummary",
    "LedgerReconcileRow",
    "LedgerReconcileResult",
]
