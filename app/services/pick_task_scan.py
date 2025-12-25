# app/services/pick_task_scan.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task_line import PickTaskLine
from app.services.pick_task_loaders import load_task

UTC = timezone.utc


async def record_scan(
    session: AsyncSession,
    *,
    task_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str],
):
    """
    扫码拣货：只更新拣货任务行（req_qty / picked_qty / batch_code），
    不直接动库存。库存扣减统一在 commit_ship 中通过 PickService 完成。
    """
    if qty == 0:
        return await load_task(session, task_id)

    task = await load_task(session, task_id, for_update=True)

    if task.status not in ("READY", "ASSIGNED", "PICKING"):
        raise ValueError(f"PickTask {task.id} status={task.status} cannot accept pick scan.")

    norm_batch = (batch_code or "").strip() or None
    target: Optional[PickTaskLine] = None
    for line in task.lines or []:
        if line.item_id == item_id and ((line.batch_code or None) == norm_batch):
            target = line
            break

    now = datetime.now(UTC)

    if target is None:
        target = PickTaskLine(
            task_id=task.id,
            order_id=None,
            order_line_id=None,
            item_id=item_id,
            req_qty=int(qty),
            picked_qty=int(qty),
            batch_code=norm_batch,
            prefer_pickface=False,
            target_location_id=None,
            status="OPEN",
            note=None,
            created_at=now,
            updated_at=now,
        )
        session.add(target)
        await session.flush()
        task.lines.append(target)
    else:
        if not target.batch_code and norm_batch:
            target.batch_code = norm_batch
        target.picked_qty = int(target.picked_qty or 0) + int(qty)
        target.updated_at = now

    if task.status in ("READY", "ASSIGNED"):
        task.status = "PICKING"
    task.updated_at = now

    await session.flush()
    return task
