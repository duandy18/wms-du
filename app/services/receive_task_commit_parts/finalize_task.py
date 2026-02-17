# app/services/receive_task_commit_parts/finalize_task.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_order import PurchaseOrder
from app.models.receive_task import ReceiveTask
from app.services.receive_task_commit_parts.po_status import recalc_po_header


async def finalize_receive_task_commit(
    session: AsyncSession,
    *,
    task: ReceiveTask,
    po: Optional[PurchaseOrder],
    touched_po_qty: bool,
    now: datetime,
) -> None:
    """
    commit 终结动作（合同层）：
    - 若回写过 PO 数量：推进 PO 头状态
    - 推进 task 状态为 COMMITTED
    - flush（由外层事务控制 commit/rollback）
    """
    if po is not None and touched_po_qty:
        recalc_po_header(po, now)

    task.status = "COMMITTED"
    await session.flush()
