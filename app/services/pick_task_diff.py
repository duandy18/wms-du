# app/services/pick_task_diff.py
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_types import PickTaskDiffLine, PickTaskDiffSummary
from app.services.pick_task_views import get_commit_lines


async def compute_diff(
    session: AsyncSession,
    *,
    task_id: int,
) -> PickTaskDiffSummary:
    """
    按 item_id 汇总差异：

    - req_qty 总量只统计 order_id 非空的行（来自订单的计划）；
    - picked_qty 总量统计所有行（包括临时拣货行）。
    """
    task, commit_lines = await get_commit_lines(session, task_id=task_id, ignore_zero=False)

    agg: Dict[int, Dict[str, int]] = {}
    for line in commit_lines:
        state = agg.setdefault(line.item_id, {"req": 0, "picked": 0})

        if line.order_id is not None:
            state["req"] += int(line.req_qty)

        state["picked"] += int(line.picked_qty)

    diff_lines: List[PickTaskDiffLine] = []
    has_over = False
    has_under = False

    for item_id, state in agg.items():
        req_total = state["req"]
        picked_total = state["picked"]
        delta = picked_total - req_total

        if delta == 0:
            status = "OK"
        elif delta < 0:
            status = "UNDER"
            has_under = True
        else:
            status = "OVER"
            has_over = True

        diff_lines.append(
            PickTaskDiffLine(
                item_id=item_id,
                req_qty=req_total,
                picked_qty=picked_total,
                delta=delta,
                status=status,
            )
        )

    return PickTaskDiffSummary(
        task_id=task_id,
        lines=diff_lines,
        has_over=has_over,
        has_under=has_under,
    )
