# tests/services/pick/test_pick_blueprint_commit_idempotency_contract.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests._problem import as_problem
from tests.services.pick._helpers_pick_blueprint import (
    PLATFORM,
    SHOP_ID,
    WAREHOUSE_ID,
    build_handoff_code,
    commit_pick_task,
    create_pick_task_from_order,
    ensure_pickable_order,
    get_pick_task,
    get_task_ref,
    ledger_count,
    scan_pick,
)


@pytest.mark.asyncio
async def test_blueprint_commit_is_only_judgment_point_and_idempotency_conflict(
    client_like,
    db_session_like_pg: AsyncSession,
) -> None:
    ledger0 = await ledger_count(db_session_like_pg)
    order_id = await ensure_pickable_order(db_session_like_pg, warehouse_id=WAREHOUSE_ID)

    task = await create_pick_task_from_order(client_like, warehouse_id=WAREHOUSE_ID, order_id=order_id)
    task_id = int(task["id"])
    task = await get_pick_task(client_like, task_id=task_id)

    order_ref = get_task_ref(task)
    handoff_code = build_handoff_code(order_ref)

    lines = task.get("lines") or []
    assert isinstance(lines, list) and len(lines) >= 1, f"pick_task has no lines: {task}"
    first = lines[0]
    item_id = int(first.get("item_id") or 0)
    assert item_id > 0, f"invalid item_id in pick_task.lines[0]: {first}"

    await scan_pick(client_like, task_id=task_id, item_id=item_id, qty=1, batch_code=first.get("batch_code"))

    r1 = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id="T-UT-1",
        allow_diff=True,
    )
    assert r1.status_code == 200, r1.text

    ledger1 = await ledger_count(db_session_like_pg)
    assert ledger1 >= ledger0 + 1, {"msg": "Commit should write stock_ledger", "before": ledger0, "after": ledger1}

    r2 = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id="T-UT-1",
        allow_diff=True,
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert isinstance(body2, dict)
    assert body2.get("status") == "OK"
    assert bool(body2.get("idempotent")) is True

    r3 = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id="T-UT-2",
        allow_diff=True,
    )
    assert r3.status_code == 409, r3.text
    p = as_problem(r3.json())
    assert p.get("error_code") == "idempotency_conflict", p
