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
# - 用于查询入参（filters），不强制影响历史数据行的实际存储值
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

    维度类：
    - item_id：商品 ID（精确）
    - item_keyword：商品关键词（模糊匹配 name / sku）
    - warehouse_id：仓库 ID
    - batch_code：批次编码

    行为类：
    - reason：原始 reason（如 OUTBOUND_SHIP）
    - reason_canon：稳定口径（RECEIPT / SHIPMENT / ADJUSTMENT）
    - sub_reason：具体动作（ORDER_SHIP / PO_RECEIPT / COUNT_ADJUST 等）

    定位类：
    - ref：关联单据（精确）
    - trace_id：追溯号（精确）

    时间类（基于 occurred_at）：
    - 普通查询：默认最近 7 天，最大 90 天
    - 历史查询：必须给 time_from，最大 3650 天（10 年）
    """

    # ---------- 维度 ----------
    item_id: Optional[int] = Field(default=None, description="商品 ID（精确）")
    item_keyword: Optional[str] = Field(
        default=None, description="商品关键词（模糊匹配 name / sku）"
    )
    warehouse_id: Optional[int] = Field(default=None, description="仓库 ID")
    batch_code: Optional[str] = Field(
        default=None, max_length=64, description="批次编码（精确）"
    )

    # ---------- 行为 ----------
    reason: Optional[str] = Field(
        default=None,
        max_length=32,
        description="原始 reason（如 OUTBOUND_SHIP / RECEIPT / ADJUSTMENT）",
    )

    # ✅ 冻结枚举：用于过滤（OpenAPI 唯一真源）
    reason_canon: Optional[ReasonCanon] = Field(
        default=None,
        description="稳定口径（RECEIPT / SHIPMENT / ADJUSTMENT）",
    )
    sub_reason: Optional[SubReason] = Field(
        default=None,
        description="具体动作（PO_RECEIPT / ORDER_SHIP / COUNT_ADJUST 等）",
    )

    # ---------- 定位 ----------
    ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="关联单据（精确匹配）",
    )
    trace_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="追溯号 trace_id（精确匹配）",
    )

    # ---------- 时间 ----------
    time_from: Optional[datetime] = Field(
        default=None, description="开始时间（含，基于 occurred_at）"
    )
    time_to: Optional[datetime] = Field(
        default=None, description="结束时间（含，基于 occurred_at）"
    )

    # ---------- 分页 ----------
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
    """
    台账明细行（展示用）：

    核心字段：
    - delta / after_qty
    - reason / reason_canon / sub_reason
    - ref / ref_line / trace_id
    - occurred_at / created_at

    维度字段：
    - warehouse_id / item_id / batch_code

    便民字段：
    - item_name（当前页 join items.name）
    - movement_type（由后端推断，用于 UI 显示）
    """

    id: int
    delta: int
    after_qty: int

    reason: str
    # ✅ 返回行保持 str：不强制影响旧数据（可能存在非 Enum 值）
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


# =========================================================
# 明细列表返回
# =========================================================
class LedgerList(_Base):
    total: int
    items: List[LedgerRow] = Field(default_factory=list)


# =========================================================
# 枚举下发（前端下拉唯一来源）
# =========================================================
class LedgerEnums(_Base):
    reason_canons: List[ReasonCanon] = Field(default_factory=list)
    sub_reasons: List[SubReason] = Field(default_factory=list)


# =========================================================
# 统计 / 对账（保留，未动）
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
