# tests/services/pick/test_pick_blueprint_insufficient_stock_contract.py
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
    force_no_stock,
    get_pick_task,
    get_task_ref,
    scan_pick,
)


@pytest.mark.asyncio
async def test_blueprint_insufficient_stock_returns_actionable_shortage_details(
    client_like,
    db_session_like_pg: AsyncSession,
) -> None:
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

    # 强制该 item/warehouse 没有任何库存，确保必定触发 insufficient_stock
    await force_no_stock(db_session_like_pg, warehouse_id=WAREHOUSE_ID, item_id=item_id)

    await scan_pick(client_like, task_id=task_id, item_id=item_id, qty=1, batch_code=first.get("batch_code"))

    r = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id="T-UT-STOCK-1",
        allow_diff=True,
    )
    assert r.status_code == 409, r.text
    p = as_problem(r.json())
    assert p.get("error_code") == "insufficient_stock", p

    details = p.get("details") or []
    assert isinstance(details, list) and len(details) >= 1, p
    d0 = details[0]
    assert isinstance(d0, dict), d0
    assert d0.get("type") == "shortage", d0

    assert isinstance(d0.get("required_qty"), int), d0
    assert isinstance(d0.get("available_qty"), int), d0
    assert isinstance(d0.get("short_qty"), int), d0

    next_actions = p.get("next_actions") or []
    assert isinstance(next_actions, list), p
    actions = {a.get("action") for a in next_actions if isinstance(a, dict)}
    assert "adjust_to_available" in actions, {"next_actions": next_actions}
