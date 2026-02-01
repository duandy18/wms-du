# app/services/pick_task_commit_ship_apply.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_service import PickService
from app.services.soft_reserve_service import SoftReserveService

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
    pick_svc = PickService()
    ref_line = 1

    for (item_id, batch_code), total_picked in agg.items():
        if total_picked <= 0:
            continue

        requires_batch = await item_requires_batch(session, item_id=int(item_id))
        bc_norm = normalize_batch_code(batch_code)

        if requires_batch and not bc_norm:
            raise ValueError(
                f"PickTask {task_id} missing batch_code for requires_batch item={item_id}; cannot commit."
            )

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
        ref_line = int(result.get("ref_line", ref_line)) + 1

    return ref_line


async def consume_soft_reserve_if_needed(
    session: AsyncSession,
    *,
    task: Any,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    order_ref: str,
    occurred_at: datetime,
    trace_id: Optional[str],
) -> None:
    if getattr(task, "source", None) == "ORDER" and order_ref.startswith(f"ORD:{platform}:{shop_id}:"):
        soft_reserve = SoftReserveService()
        await soft_reserve.pick_consume(
            session=session,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=int(warehouse_id),
            ref=order_ref,
            occurred_at=occurred_at,
            trace_id=trace_id,
        )


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
