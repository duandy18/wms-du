# app/services/pick_task_commit_ship_problems.py
from __future__ import annotations

from typing import Any, Dict, Optional

from app.api.problem import raise_problem


def raise_idempotency_conflict(
    *,
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    existing_trace_id: str,
    incoming_trace_id: str,
) -> None:
    raise_problem(
        status_code=409,
        error_code="idempotency_conflict",
        message="幂等冲突：该订单已提交过出库，但 trace_id 不一致，禁止重复提交。",
        context={
            "task_id": int(task_id),
            "warehouse_id": int(warehouse_id),
            "ref": str(order_ref),
            "existing_trace_id": str(existing_trace_id),
            "incoming_trace_id": str(incoming_trace_id),
        },
        details=[
            {
                "type": "idempotency",
                "path": "trace_id",
                "reason": "trace_id_mismatch",
            }
        ],
        next_actions=[
            {"action": "view_trace", "label": "查看已提交记录"},
            {"action": "rescan_order", "label": "重新扫码订单"},
        ],
    )


def raise_handoff_mismatch(
    *,
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    handoff_reason: str,
    expected_handoff_code: Optional[str],
    got_handoff_code: Optional[str],
) -> None:
    """
    handoff 的失败输出必须结构化：reason/expected/got 进入 context，
    details.reason 使用稳定 reason_code（前端不需要解析字符串）。
    """
    ctx: Dict[str, Any] = {
        "task_id": int(task_id),
        "warehouse_id": int(warehouse_id),
        "ref": str(order_ref),
        "handoff_reason": str(handoff_reason),
    }
    if expected_handoff_code is not None:
        ctx["expected_handoff_code"] = str(expected_handoff_code)
    if got_handoff_code is not None:
        ctx["got_handoff_code"] = str(got_handoff_code)

    raise_problem(
        status_code=409,
        error_code="handoff_code_mismatch",
        message="订单核对失败（确认码不匹配），禁止提交。",
        context=ctx,
        details=[
            {
                "type": "state",
                "path": "handoff_code",
                "reason": str(handoff_reason),
            }
        ],
        next_actions=[
            {"action": "rescan_order", "label": "重新扫码订单"},
            {"action": "continue_pick", "label": "返回拣货继续检查"},
        ],
    )


def raise_diff_not_allowed(
    *,
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    diffs: list[Dict[str, Any]] | None = None,
) -> None:
    raise_problem(
        status_code=422,
        error_code="diff_not_allowed",
        message="欠拣/超拣不允许提交。",
        context={
            "task_id": int(task_id),
            "warehouse_id": int(warehouse_id),
            "ref": str(order_ref),
        },
        details=diffs or [{"type": "diff", "path": "diff", "reason": "OVER/UNDER"}],
        next_actions=[
            {"action": "continue_pick", "label": "继续拣货"},
            {"action": "void_session", "label": "作废本次拣货"},
            {"action": "go_exception_flow", "label": "转异常流程"},
        ],
    )


def raise_empty_pick_lines(*, task_id: int, order_ref: str) -> None:
    raise_problem(
        status_code=422,
        error_code="empty_pick_lines",
        message="未采集任何拣货事实，禁止提交。",
        context={"task_id": int(task_id), "ref": str(order_ref)},
        details=[{"type": "validation", "path": "commit_lines", "reason": "empty"}],
        next_actions=[{"action": "continue_pick", "label": "继续拣货"}],
    )
