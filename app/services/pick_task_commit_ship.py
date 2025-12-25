# app/services/pick_task_commit_ship.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_service import PickService
from app.services.soft_reserve_service import SoftReserveService

from app.services.pick_task_diff import compute_diff
from app.services.pick_task_loaders import load_task
from app.services.pick_task_views import get_commit_lines

UTC = timezone.utc


async def commit_ship(
    session: AsyncSession,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
) -> Dict[str, Any]:
    """
    拣货任务提交（Golden Flow 版）：
    - 通过 PickService.record_pick 扣减库存（MovementType.PICK）；
    - 通过 SoftReserveService.pick_consume 消耗该订单 ref 的软预占；
    - 写 outbound_commits_v2 标记“出库提交完成”；
    - 标记任务及明细为 DONE。
    """
    task = await load_task(session, task_id, for_update=True)

    diff_summary = await compute_diff(session, task_id=task.id)

    if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
        raise ValueError(
            f"PickTask {task.id} has diff (OVER/UNDER), commit is not allowed in strict mode."
        )

    task, commit_lines = await get_commit_lines(session, task_id=task.id, ignore_zero=True)
    if not commit_lines:
        raise ValueError(f"PickTask {task.id} has no picked_qty > 0, cannot commit.")

    plat = platform.upper()
    shop = str(shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")
    occurred_at = datetime.now(UTC)

    pick_svc = PickService()
    soft_reserve = SoftReserveService()

    from typing import Tuple as _Tuple  # 避免和上面 type hints 混淆

    agg: Dict[_Tuple[int, Optional[str]], int] = {}
    for line in commit_lines:
        key = (line.item_id, (line.batch_code or None))
        agg[key] = agg.get(key, 0) + line.picked_qty

    ref_line = 1

    for (item_id, batch_code), total_picked in agg.items():
        if total_picked <= 0:
            continue
        if not batch_code:
            raise ValueError(
                f"PickTask {task.id} has picked_qty for item={item_id} "
                f"but missing batch_code; cannot commit safely."
            )

        result = await pick_svc.record_pick(
            session=session,
            item_id=item_id,
            qty=total_picked,
            ref=order_ref,
            occurred_at=occurred_at,
            batch_code=batch_code,
            warehouse_id=wh_id,
            trace_id=trace_id,
            start_ref_line=ref_line,
        )
        ref_line = int(result.get("ref_line", ref_line)) + 1

    if task.source == "ORDER" and order_ref.startswith(f"ORD:{plat}:{shop}:"):
        await soft_reserve.pick_consume(
            session=session,
            platform=plat,
            shop_id=shop,
            warehouse_id=wh_id,
            ref=order_ref,
            occurred_at=occurred_at,
            trace_id=trace_id,
        )

    eff_trace_id = trace_id or order_ref
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
        {
            "platform": plat,
            "shop_id": shop,
            "ref": order_ref,
            "trace_id": eff_trace_id,
        },
    )

    now = datetime.now(UTC)
    task.status = "DONE"
    task.updated_at = now
    for line in task.lines or []:
        line.status = "DONE"
        line.updated_at = now

    await session.flush()

    return {
        "status": "OK",
        "task_id": task.id,
        "warehouse_id": wh_id,
        "platform": plat,
        "shop_id": shop,
        "ref": order_ref,
        "diff": {
            "task_id": diff_summary.task_id,
            "has_over": diff_summary.has_over,
            "has_under": diff_summary.has_under,
            "lines": [asdict(x) for x in diff_summary.lines],
        },
    }
