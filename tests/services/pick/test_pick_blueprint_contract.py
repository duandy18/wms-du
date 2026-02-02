# tests/services/pick/test_pick_blueprint_contract.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services.pick._helpers_pick_blueprint import (
    WAREHOUSE_ID,
    create_pick_task_from_order,
    ensure_pickable_order,
    get_pick_task,
    ledger_count,
    scan_pick,
    stocks_count,
)


@pytest.mark.asyncio
async def test_blueprint_pick_does_not_touch_ledger_or_stocks(
    client_like,
    db_session_like_pg: AsyncSession,
) -> None:
    ledger0 = await ledger_count(db_session_like_pg)
    stocks0 = await stocks_count(db_session_like_pg)

    order_id = await ensure_pickable_order(db_session_like_pg, warehouse_id=WAREHOUSE_ID)

    task = await create_pick_task_from_order(client_like, warehouse_id=WAREHOUSE_ID, order_id=order_id)
    task_id = int(task["id"])
    task = await get_pick_task(client_like, task_id=task_id)

    lines = task.get("lines") or []
    assert isinstance(lines, list) and len(lines) >= 1, f"pick_task has no lines: {task}"
    first = lines[0]
    item_id = int(first.get("item_id") or 0)
    assert item_id > 0, f"invalid item_id in pick_task.lines[0]: {first}"

    await scan_pick(client_like, task_id=task_id, item_id=item_id, qty=1, batch_code=first.get("batch_code"))

    ledger1 = await ledger_count(db_session_like_pg)
    stocks1 = await stocks_count(db_session_like_pg)

    assert ledger1 == ledger0, {"msg": "Pick(scan) must not write stock_ledger", "before": ledger0, "after": ledger1}
    assert stocks1 == stocks0, {"msg": "Pick(scan) must not change stocks rows", "before": stocks0, "after": stocks1}
