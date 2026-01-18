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


async def _load_existing_outbound_commit_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> Optional[str]:
    """
    幂等辅助：若 outbound_commits_v2 已存在，则读取其 trace_id（用于返回给前端做联动追溯）。
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT trace_id
                  FROM outbound_commits_v2
                 WHERE platform = :platform
                   AND shop_id  = :shop_id
                   AND ref      = :ref
                 ORDER BY created_at DESC, updated_at DESC
                 LIMIT 1
                """
            ),
            {"platform": platform, "shop_id": shop_id, "ref": ref},
        )
    ).first()
    if not row:
        return None
    try:
        return str(row[0]) if row[0] else None
    except Exception:
        return None


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

    ✅ Phase-3 延展：现实世界“最后扫码确认”会导致重复触发 commit，
    因此这里必须具备强幂等：
      - 若 task 已 DONE：直接短路返回（不再扣库存、不再消耗预占）
      - 若 outbound_commits_v2 已存在：同样短路返回
    """
    task = await load_task(session, task_id, for_update=True)

    plat = platform.upper()
    shop = str(shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")

    # ---------------- ✅ 幂等短路：DONE 终态 / 已有 outbound_commits_v2 ----------------
    if str(getattr(task, "status", "")).upper() == "DONE":
        existing_tid = await _load_existing_outbound_commit_trace_id(
            session, platform=plat, shop_id=shop, ref=order_ref
        )
        return {
            "status": "OK",
            "idempotent": True,
            "task_id": task.id,
            "warehouse_id": wh_id,
            "platform": plat,
            "shop_id": shop,
            "ref": order_ref,
            "trace_id": existing_tid or trace_id or order_ref,
            "diff": {
                "task_id": task.id,
                "has_over": False,
                "has_under": False,
                "lines": [],
            },
        }

    existing_tid = await _load_existing_outbound_commit_trace_id(
        session, platform=plat, shop_id=shop, ref=order_ref
    )
    if existing_tid:
        # outbound_commits_v2 已存在：视为已经完成的出库提交
        task.status = "DONE"
        task.updated_at = datetime.now(UTC)
        for line in task.lines or []:
            line.status = "DONE"
            line.updated_at = task.updated_at
        await session.flush()

        return {
            "status": "OK",
            "idempotent": True,
            "task_id": task.id,
            "warehouse_id": wh_id,
            "platform": plat,
            "shop_id": shop,
            "ref": order_ref,
            "trace_id": existing_tid,
            "diff": {
                "task_id": task.id,
                "has_over": False,
                "has_under": False,
                "lines": [],
            },
        }

    # ---------------- diff 校验（严格模式可拒绝 OVER/UNDER） ----------------
    diff_summary = await compute_diff(session, task_id=task.id)
    if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
        raise ValueError(
            f"PickTask {task.id} has diff (OVER/UNDER), commit is not allowed in strict mode."
        )

    # ---------------- 生成 commit 行（只认 picked_qty > 0） ----------------
    task, commit_lines = await get_commit_lines(session, task_id=task.id, ignore_zero=True)
    if not commit_lines:
        raise ValueError(f"PickTask {task.id} has no picked_qty > 0, cannot commit.")

    occurred_at = datetime.now(UTC)

    pick_svc = PickService()
    soft_reserve = SoftReserveService()

    from typing import Tuple as _Tuple  # 避免和上面 type hints 混淆

    # 聚合：同 item + batch 合并成一次扣减（保持现实“拣货单”语义）
    agg: Dict[_Tuple[int, Optional[str]], int] = {}
    for line in commit_lines:
        key = (line.item_id, (line.batch_code or None))
        agg[key] = agg.get(key, 0) + line.picked_qty

    ref_line = 1

    # ---------------- 1) 扣库存（PICK 语义，写 ledger + stocks） ----------------
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

    # ---------------- 2) 消耗软预占（仅 ORDER 且 ref 符合 ORD:...） ----------------
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

    # ---------------- 3) 标记 outbound_commits_v2（幂等：ON CONFLICT DO NOTHING） ----------------
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

    # ---------------- 4) DONE 终态 ----------------
    now = datetime.now(UTC)
    task.status = "DONE"
    task.updated_at = now
    for line in task.lines or []:
        line.status = "DONE"
        line.updated_at = now

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
