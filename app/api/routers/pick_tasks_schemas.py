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
        description="拣货仓库 ID；缺省用订单上的 warehouse_id，若为空则 fallback=1",
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


class PickTaskScanIn(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., gt=0, description="本次拣货数量（>0）")
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选；若为空，后续 commit_ship 会拒绝执行）",
    )


class PickTaskCommitIn(BaseModel):
    platform: str = Field(..., description="平台标识，如 PDD / TAOBAO")
    shop_id: str = Field(..., description="店铺 ID（字符串）")
    handoff_code: str = Field(
        ...,
        min_length=1,
        description="订单确认码（WMS / 扫码枪输入）；v1: WMS:ORDER:v1:{platform}:{shop_id}:{ext_order_no}",
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

    task_id: int
    warehouse_id: int
    platform: str
    shop_id: str
    ref: str

    diff: Dict[str, Any]
