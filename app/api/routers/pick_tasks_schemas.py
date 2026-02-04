# app/api/routers/pick_tasks_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


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

    # ✅ 展示型纯函数字段：前端不再推导
    @computed_field  # type: ignore[misc]
    @property
    def remain_qty(self) -> int:
        # remain = req - picked；允许为负（表示 OVER）
        return int(self.req_qty) - int(self.picked_qty)

    @computed_field  # type: ignore[misc]
    @property
    def delta(self) -> int:
        # 与 diff 接口语义一致：delta = picked - req
        return int(self.picked_qty) - int(self.req_qty)

    @computed_field  # type: ignore[misc]
    @property
    def diff_status(self) -> str:
        d = self.delta
        if d > 0:
            return "over"
        if d < 0:
            return "under"
        return "ok"

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


class GateOut(BaseModel):
    """
    后端裁决门禁（稳定合同）：
    - allowed: 前端直接用来禁用按钮/输入
    - error_code/message/details/next_actions：与 Problem 体系同源（前端无需猜/无需解析字符串）
    """

    allowed: bool
    error_code: Optional[str] = None
    message: Optional[str] = None
    details: List[Dict[str, Any]] = Field(default_factory=list)
    next_actions: List[Dict[str, Any]] = Field(default_factory=list)


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
    lines: List[PickTaskLineOut] = Field(default_factory=list)

    # ✅ 可观测闭环：最近一次 pick_list print_job（若存在）
    print_job: Optional[PrintJobOut] = None

    # ✅ 汇总：前端不再推导 totals/has_over/has_under
    @computed_field  # type: ignore[misc]
    @property
    def req_total(self) -> int:
        return sum(int(ln.req_qty) for ln in (self.lines or []))

    @computed_field  # type: ignore[misc]
    @property
    def picked_total(self) -> int:
        return sum(int(ln.picked_qty) for ln in (self.lines or []))

    @computed_field  # type: ignore[misc]
    @property
    def remain_total(self) -> int:
        return int(self.req_total) - int(self.picked_total)

    @computed_field  # type: ignore[misc]
    @property
    def has_over(self) -> bool:
        return any((ln.delta > 0) for ln in (self.lines or []))

    @computed_field  # type: ignore[misc]
    @property
    def has_under(self) -> bool:
        return any((ln.delta < 0) for ln in (self.lines or []))

    # ✅ 门禁：scan（与 pick_task_scan.py 的裁决一致）
    @computed_field  # type: ignore[misc]
    @property
    def scan_gate(self) -> GateOut:
        allowed_status = {"NEW", "READY", "ASSIGNED", "PICKING"}
        if str(self.status) in allowed_status:
            return GateOut(allowed=True)

        return GateOut(
            allowed=False,
            error_code="pick_task_scan_reject",
            message="当前任务状态不允许扫码拣货。",
            details=[
                {
                    "type": "guard",
                    "guard": "scan",
                    "task_id": int(self.id),
                    "status": str(self.status),
                    "allowed": sorted(list(allowed_status)),
                    "reason": "status_not_allowed",
                }
            ],
            next_actions=[
                {"action": "view_task", "label": "查看任务详情"},
                {"action": "back_to_list", "label": "返回任务列表"},
            ],
        )

    # ✅ 门禁：commit（主线假设 allow_diff=True；diff_not_allowed 只在 allow_diff=False 场景触发）
    @computed_field  # type: ignore[misc]
    @property
    def commit_gate(self) -> GateOut:
        # 1) 状态门禁（DONE 等终态不允许提交）
        if str(self.status) == "DONE":
            return GateOut(
                allowed=False,
                error_code="pick_task_commit_reject",
                message="任务已完成，禁止重复提交。",
                details=[{"type": "state", "path": "status", "reason": "already_done", "status": str(self.status)}],
                next_actions=[{"action": "view_outbound", "label": "查看出库记录"}],
            )

        # 2) 空提交门禁：picked_qty>0 的行不存在 ⇒ empty_pick_lines（与 problems.py 同源）
        has_any_picked = any(int(ln.picked_qty or 0) > 0 for ln in (self.lines or []))
        if not has_any_picked:
            return GateOut(
                allowed=False,
                error_code="empty_pick_lines",
                message="未采集任何拣货事实，禁止提交。",
                details=[{"type": "validation", "path": "commit_lines", "reason": "empty"}],
                next_actions=[{"action": "continue_pick", "label": "继续拣货"}],
            )

        # 3) 主线 allow_diff=True：OVER/UNDER 不作为门禁
        return GateOut(allowed=True)

    model_config = ConfigDict(from_attributes=True)


class PickTaskCommitCheckOut(BaseModel):
    """
    只读预检输出（与 Problem 体系同源）：
    - 前端可复用同一套 Problem 渲染组件，不需要做字段映射
    """

    allowed: bool
    error_code: Optional[str] = None
    message: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    details: List[Dict[str, Any]] = Field(default_factory=list)
    next_actions: List[Dict[str, Any]] = Field(default_factory=list)

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


# ✅ commit 返回 diff 的强类型（替换 Dict[str,Any]）
class PickTaskCommitDiffLineOut(BaseModel):
    item_id: int
    req_qty: int
    picked_qty: int
    delta: int
    status: str


class PickTaskCommitDiffOut(BaseModel):
    task_id: int
    has_over: bool
    has_under: bool
    has_temp_lines: bool
    temp_lines_n: int
    lines: List[PickTaskCommitDiffLineOut]


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

    diff: PickTaskCommitDiffOut

    # ✅ 成功路径也给出可行动提示（与 Problem 的 next_actions 同源风格）
    next_actions: List[Dict[str, Any]] = Field(default_factory=list)
