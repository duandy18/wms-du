# app/services/pick_task_commit_ship_apply.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.services.pick_service import PickService

from app.services.pick_task_commit_ship_requirements import item_requires_batch, normalize_batch_code


def build_agg_from_commit_lines(commit_lines: Any) -> Dict[Tuple[int, Optional[str]], int]:
    agg: Dict[Tuple[int, Optional[str]], int] = {}
    for line in commit_lines:
        key = (int(line.item_id), (line.batch_code or None))
        agg[key] = agg.get(key, 0) + int(line.picked_qty)
    return agg


async def apply_stock_deductions(
    session: AsyncSession,
    *,
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    occurred_at: datetime,
    agg: Dict[Tuple[int, Optional[str]], int],
    trace_id: Optional[str],
) -> int:
    """
    主线裁决：扣库存 + 写台账（通过 PickService.record_pick）。

    关键合同：
    - HTTPException(detail=Problem) 必须原样透传（避免 details/next_actions 丢失）
    - 其它未知异常统一收敛为 500 Problem（系统异常）
    - 绝不使用 “raise_problem(...) from e”（语法非法）
    """
    pick_svc = PickService()
    ref_line = 1

    for (item_id, batch_code), total_picked in agg.items():
        if total_picked <= 0:
            continue

        requires_batch = await item_requires_batch(session, item_id=int(item_id))
        bc_norm = normalize_batch_code(batch_code)

        if requires_batch and not bc_norm:
            raise_problem(
                status_code=422,
                error_code="batch_required",
                message="批次受控商品必须提供批次，禁止提交。",
                context={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                },
                details=[
                    {
                        "type": "batch",
                        "path": f"commit_lines[item_id={int(item_id)}]",
                        "item_id": int(item_id),
                        "batch_code": None,
                        "reason": "requires_batch",
                    }
                ],
                next_actions=[
                    {"action": "edit_batch", "label": "补录/更正批次"},
                    {"action": "continue_pick", "label": "继续拣货"},
                ],
            )

        try:
            result = await pick_svc.record_pick(
                session=session,
                item_id=int(item_id),
                qty=int(total_picked),
                ref=order_ref,
                occurred_at=occurred_at,
                batch_code=bc_norm,
                warehouse_id=int(warehouse_id),
                trace_id=trace_id,
                start_ref_line=ref_line,
            )
        except HTTPException:
            # PickService.record_pick 已经按 Problem 合同抛出（如 409 insufficient_stock），直接透传
            raise
        except Exception as e:
            # 其它未知异常：统一 500 Problem（系统异常）
            raise_problem(
                status_code=500,
                error_code="pick_apply_failed",
                message="拣货扣减失败：系统异常。",
                context={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                    "batch_code": bc_norm,
                },
                details=[
                    {"type": "state", "path": "apply_stock_deductions", "reason": str(e)}
                ],
            )

        ref_line = int(result.get("ref_line", ref_line)) + 1

    return ref_line


async def write_outbound_commit_v2(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
) -> None:
    await session.execute(
        SA(
            """
            INSERT INTO outbound_commits_v2 (
                platform,
                shop_id,
                ref,
                state,
                created_at,
                updated_at,
                trace_id
            )
            VALUES (
                :platform,
                :shop_id,
                :ref,
                'COMPLETED',
                now(),
                now(),
                :trace_id
            )
            ON CONFLICT (platform, shop_id, ref) DO NOTHING
            """
        ),
        {"platform": platform, "shop_id": shop_id, "ref": ref, "trace_id": trace_id},
    )
