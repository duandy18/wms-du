# app/services/receive_task_commit.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.receive_task_loaders import load_item_policy_map
from app.services.receive_task_query import get_with_lines

from app.services.receive_task_commit_parts.apply_lines import apply_task_lines
from app.services.receive_task_commit_parts.finalize_task import finalize_receive_task_commit
from app.services.receive_task_commit_parts.order_return_side_effects import (
    handle_order_return_side_effects,
)
from app.services.receive_task_commit_parts.po_loader import load_po_and_lines_map
from app.services.receive_task_commit_parts.receipt_facts import make_ref, make_sub_reason
from app.services.receive_task_commit_parts.validations import (
    choose_now,
    validate_lines_shelf_life,
    validate_task_before_commit,
)
from app.services.receive_task_commit_parts.verify_after_commit import verify_after_receive_commit


async def commit(
    session: AsyncSession,
    *,
    inbound_svc: InboundService,
    task_id: int,
    trace_id: Optional[str] = None,
    occurred_at=None,
    utc=None,
):
    task = await get_with_lines(session, task_id, for_update=True)
    validate_task_before_commit(task)

    item_ids = sorted({int(line.item_id) for line in task.lines if line.item_id})
    policy_map = await load_item_policy_map(session, item_ids)
    validate_lines_shelf_life(task, policy_map)

    now = choose_now(occurred_at, utc)

    ref = make_ref(task)
    sub_reason = make_sub_reason(task)

    po, po_lines_map = await load_po_and_lines_map(session, po_id=task.po_id)

    _receipt, _ref_line_counter, effects, returned_by_item, touched_po_qty = await apply_task_lines(
        session,
        inbound_svc=inbound_svc,
        task=task,
        po_lines_map=po_lines_map,
        ref=str(ref),
        sub_reason=str(sub_reason),
        trace_id=trace_id,
        now=now,
    )

    await finalize_receive_task_commit(
        session,
        task=task,
        po=po,
        touched_po_qty=touched_po_qty,
        now=now,
    )

    await verify_after_receive_commit(
        session,
        warehouse_id=int(task.warehouse_id),
        ref=str(ref),
        effects=effects,
        at=now,
    )

    if task.source_type == "ORDER" and task.source_id:
        await handle_order_return_side_effects(
            session,
            order_id=int(task.source_id),
            warehouse_id=int(task.warehouse_id),
            ref_fallback=str(ref),
            returned_by_item=returned_by_item,
            trace_id=str(trace_id) if trace_id else None,
        )

    return task
