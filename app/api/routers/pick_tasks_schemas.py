# app/api/routers/pick_tasks_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PickTaskLineOut(BaseModel):
    id: int
    task_id: int
    order_id: Optional[int]
    order_line_id: Optional[int]
    item_id: int
    req_qty: int
    picked_qty: int
    batch_code: Optional[str]
    status: str
    note: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrintJobOut(BaseModel):
    id: int
    kind: str
    ref_type: str
    ref_id: int
    status: str
    payload: Dict[str, Any]
    requested_at: datetime
    printed_at: Optional[datetime]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime


class PickTaskOut(BaseModel):
    id: int
    warehouse_id: int
    ref: Optional[str]
    source: Optional[str]
    priority: int
    status: str
    assigned_to: Optional[str]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
    lines: List[PickTaskLineOut] = []

    # ✅ 可观测闭环：最近一次 pick_list print_job（若存在）
    print_job: Optional[PrintJobOut] = None

    model_config = ConfigDict(from_attributes=True)


class PickTaskCreateFromOrder(BaseModel):
    warehouse_id: Optional[int] = Field(
        None,
        description="拣货仓库 ID；手工模式必须显式提供。",
    )
    source: str = Field(
        "ORDER",
        description="任务来源标记（默认 'ORDER'）",
    )
    priority: int = Field(
        100,
        ge=0,
        description="任务优先级（整数，越小越高，一般 100 即可）",
    )


class PickTaskPrintPickListIn(BaseModel):
    order_id: int = Field(..., ge=1, description="订单 ID（手工触发打印必须显式提供）")
    trace_id: Optional[str] = Field(
        None,
        description="可选：打印 payload 里的 trace_id；为空则使用订单 trace_id（如果存在）",
    )


class PickTaskScanIn(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., gt=0, description="本次拣货数量（>0）")
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选；若为空，后续 commit_ship 会按批次规则决定是否拒绝）",
    )


class PickTaskCommitIn(BaseModel):
    platform: str = Field(..., description="平台标识，如 PDD / TAOBAO")
    shop_id: str = Field(..., description="店铺 ID（字符串）")

    # ✅ Phase 2：删除确认码（handoff_code）
    # - 不再强制二次确认码作为门禁
    # - 若调用方仍传 handoff_code（兼容旧客户端），后端仅在其非空时做一致性校验
    handoff_code: Optional[str] = Field(
        None,
        description="（已废弃/兼容字段）订单确认码。新主线不需要；若传入则会做一致性校验。",
    )

    trace_id: Optional[str] = Field(
        None,
        description="链路 trace_id，可选；若空则由服务层 fallback 到 ref",
    )
    allow_diff: bool = Field(
        True,
        description="是否允许在存在 OVER/UNDER 的情况下仍然 commit 出库",
    )


class PickTaskDiffLineOut(BaseModel):
    item_id: int
    req_qty: int
    picked_qty: int
    delta: int
    status: str


class PickTaskDiffSummaryOut(BaseModel):
    task_id: int
    has_over: bool
    has_under: bool
    lines: List[PickTaskDiffLineOut]


class PickTaskCommitResult(BaseModel):
    status: str

    # ✅ 蓝皮书合同字段：幂等与链路
    idempotent: bool = Field(
        False,
        description="是否为幂等重放结果（True 表示未重复落账/未重复扣库）",
    )
    trace_id: Optional[str] = Field(
        None,
        description="本次提交最终使用的 trace_id（幂等重放时为已存在的 trace_id）",
    )

    # ✅ 可观测：提交时间（ISO8601 字符串，UTC）
    committed_at: Optional[str] = Field(
        None,
        description="本次提交时间（ISO8601，UTC；幂等重放时为首次提交 created_at）",
    )

    task_id: int
    warehouse_id: int
    platform: str
    shop_id: str
    ref: str

    diff: Dict[str, Any]
