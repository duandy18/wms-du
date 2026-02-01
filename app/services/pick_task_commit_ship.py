# app/services/pick_task_commit_ship.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_diff import compute_diff
from app.services.pick_task_loaders import load_task
from app.services.pick_task_views import get_commit_lines

from app.services.pick_task_commit_ship_handoff import assert_handoff_code_match
from app.services.pick_task_commit_ship_idempotency import (
    build_idempotent_ok_payload,
    load_existing_outbound_commit_trace_id,
    mark_task_done_inplace,
)
from app.services.pick_task_commit_ship_apply import (
    apply_stock_deductions,
    build_agg_from_commit_lines,
    consume_soft_reserve_if_needed,
    write_outbound_commit_v2,
)

UTC = timezone.utc


async def commit_ship(
    session: AsyncSession,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    handoff_code: str,
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
) -> Dict[str, Any]:
    task = await load_task(session, task_id, for_update=True)

    plat = platform.upper()
    shop = str(shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")

    # 1) 最后扫码确认
    assert_handoff_code_match(order_ref=order_ref, handoff_code=handoff_code)

    # 2) 幂等短路：DONE 终态
    if str(getattr(task, "status", "")).upper() == "DONE":
        existing_tid = await load_existing_outbound_commit_trace_id(
            session, platform=plat, shop_id=shop, ref=order_ref
        )
        return build_idempotent_ok_payload(
            task_id=task.id,
            warehouse_id=wh_id,
            platform=plat,
            shop_id=shop,
            ref=order_ref,
            trace_id=existing_tid or trace_id or order_ref,
        )

    # 3) 幂等短路：outbound_commits_v2 已存在
    existing_tid = await load_existing_outbound_commit_trace_id(
        session, platform=plat, shop_id=shop, ref=order_ref
    )
    if existing_tid:
        now = datetime.now(UTC)
        await mark_task_done_inplace(task=task, now=now)
        await session.flush()
        return build_idempotent_ok_payload(
            task_id=task.id,
            warehouse_id=wh_id,
            platform=plat,
            shop_id=shop,
            ref=order_ref,
            trace_id=existing_tid,
        )

    # 4) diff 校验
    diff_summary = await compute_diff(session, task_id=task.id)
    if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
        raise ValueError(
            f"PickTask {task.id} has diff (OVER/UNDER), commit is not allowed in strict mode."
        )

    # 5) 生成 commit 行（picked_qty>0）
    task, commit_lines = await get_commit_lines(session, task_id=task.id, ignore_zero=True)
    if not commit_lines:
        raise ValueError(f"PickTask {task.id} has no picked_qty > 0, cannot commit.")

    occurred_at = datetime.now(UTC)

    # 6) 聚合 + 扣库存
    agg = build_agg_from_commit_lines(commit_lines)
    await apply_stock_deductions(
        session,
        task_id=task.id,
        warehouse_id=wh_id,
        order_ref=order_ref,
        occurred_at=occurred_at,
        agg=agg,
        trace_id=trace_id,
    )

    # 7) consume soft reserve
    await consume_soft_reserve_if_needed(
        session,
        task=task,
        platform=plat,
        shop_id=shop,
        warehouse_id=wh_id,
        order_ref=order_ref,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )

    # 8) 写 outbound_commits_v2
    eff_trace_id = trace_id or order_ref
    await write_outbound_commit_v2(
        session,
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=eff_trace_id,
    )

    # 9) DONE 终态
    now = datetime.now(UTC)
    await mark_task_done_inplace(task=task, now=now)
    await session.flush()

    return {
        "status": "OK",
        "idempotent": False,
        "task_id": task.id,
        "warehouse_id": wh_id,
        "platform": plat,
        "shop_id": shop,
        "ref": order_ref,
        "trace_id": eff_trace_id,
        "diff": {
            "task_id": diff_summary.task_id,
            "has_over": diff_summary.has_over,
            "has_under": diff_summary.has_under,
            "lines": [asdict(x) for x in diff_summary.lines],
        },
    }
