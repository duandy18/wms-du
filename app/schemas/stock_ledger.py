from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    """
    通用基类：
    - from_attributes: 支持 SQLAlchemy ORM 自动序列化；
    - extra = ignore: 忽略旧字段；
    - populate_by_name: 支持 alias。
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 查询入参（明细 / 统计 / 对账 共用） =========
class LedgerQuery(_Base):
    """
    台账查询 / 统计 / 对账过滤条件：

    - item_id：精确商品 ID；
    - item_keyword：模糊匹配 items.name / items.sku（二者二选一使用）；
    - warehouse_id / batch_code：按仓、按批次过滤；
    - reason / ref / trace_id：按动账原因、业务引用、链路 ID 过滤；
    - 时间：基于 occurred_at 的时间窗口（留空则由后端补“最近 7 天”）。
    """

    item_id: Optional[int] = Field(default=None, description="商品 ID（精确）")
    item_keyword: Optional[str] = Field(
        default=None,
        description="商品关键词（模糊匹配 name/sku）",
    )

    warehouse_id: Optional[int] = Field(default=None, description="仓库 ID")
    batch_code: Optional[str] = Field(
        default=None,
        max_length=64,
        description="批次编码（精确匹配）",
    )

    reason: Optional[str] = Field(
        default=None,
        max_length=32,
        description="原因（RECEIPT / COUNT / ADJUSTMENT / SHIP / SHIPMENT 等）",
    )
    ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="业务引用（scan_ref / order_ref 等，精确匹配）",
    )
    trace_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="链路 trace_id（通常由 Trace 页面跳转时使用）",
    )

    time_from: Optional[datetime] = Field(
        default=None,
        description="开始时间（含，基于 occurred_at）；留空则由后端自动补",
    )
    time_to: Optional[datetime] = Field(
        default=None,
        description="结束时间（含，基于 occurred_at）；留空则由后端自动补",
    )

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


# ========= 单条台账记录（明细） =========
class LedgerRow(_Base):
    """
    v2 Ledger 真实字段：
    - id / item_id / warehouse_id / batch_code
    - delta / after_qty / reason / ref / ref_line / trace_id
    - occurred_at / created_at
    """

    id: int
    delta: int
    reason: str
    ref: Optional[str] = None
    ref_line: int

    occurred_at: datetime
    created_at: datetime

    after_qty: int

    item_id: int
    warehouse_id: int
    batch_code: str

    trace_id: Optional[str] = None
    movement_type: Optional[str] = None  # 预留，当前为 null


# ========= 明细列表返回 =========
class LedgerList(_Base):
    """
    台账明细查询结果：
    - total：符合过滤条件的总条数；
    - items：当前页明细。
    """

    total: int
    items: list[LedgerRow] = Field(default_factory=list)


# ========= 统计结果（给统计图/表用） =========
class LedgerReasonStat(_Base):
    """
    按 reason 聚合的统计行。
    """

    reason: str
    count: int
    total_delta: int


class LedgerSummary(_Base):
    """
    台账统计结果（供前端直接渲染统计表/图）：

    - filters：本次统计使用的过滤条件（用于回显）；
    - by_reason：按 reason 聚合的统计；
    - net_delta：在当前过滤条件下 sum(delta)。
    """

    filters: LedgerQuery
    by_reason: List[LedgerReasonStat] = Field(default_factory=list)
    net_delta: int


# ========= 对账结果 =========
class LedgerReconcileRow(_Base):
    """
    台账对账结果的一行：
    - warehouse_id / item_id / batch_code：库存维度；
    - ledger_sum_delta: 台账中 SUM(delta)；
    - stock_qty: stocks 表当前 qty；
    - diff: ledger_sum_delta - stock_qty（非 0 表示不平）。
    """

    warehouse_id: int
    item_id: int
    batch_code: str

    ledger_sum_delta: int
    stock_qty: int
    diff: int


class LedgerReconcileResult(_Base):
    """
    台账对账结果：
    - rows: 所有发现不平账的记录。
    """

    rows: list[LedgerReconcileRow] = Field(default_factory=list)


__all__ = [
    "LedgerQuery",
    "LedgerRow",
    "LedgerList",
    "LedgerReasonStat",
    "LedgerSummary",
    "LedgerReconcileRow",
    "LedgerReconcileResult",
]
