# tests/services/test_pick_commit_idempotent_shape.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService
from tests.services.pick._helpers_pick_blueprint import (
    PLATFORM,
    SHOP_ID,
    WAREHOUSE_ID,
    commit_pick_task,
    create_pick_task_from_order,
    ensure_pickable_order,
    pick_any_item_id,
    scan_pick,
)

UTC = timezone.utc


def _assert_commit_ok_shape(x: dict) -> None:
    assert isinstance(x, dict)

    for k in (
        "status",
        "idempotent",
        "task_id",
        "warehouse_id",
        "platform",
        "shop_id",
        "ref",
        "trace_id",
        "committed_at",
        "diff",
    ):
        assert k in x, f"missing field: {k}"

    assert x["status"] == "OK"
    assert isinstance(x["idempotent"], bool)
    assert isinstance(x["task_id"], int)
    assert isinstance(x["warehouse_id"], int)
    assert isinstance(x["platform"], str) and x["platform"]
    assert isinstance(x["shop_id"], str)
    assert isinstance(x["ref"], str) and x["ref"]
    assert isinstance(x["trace_id"], str) and x["trace_id"]
    assert isinstance(x["committed_at"], str) and x["committed_at"]

    d = x["diff"]
    assert isinstance(d, dict)
    for k in ("task_id", "has_over", "has_under", "has_temp_lines", "temp_lines_n", "lines"):
        assert k in d, f"missing diff field: {k}"
    assert isinstance(d["task_id"], int)
    assert isinstance(d["has_over"], bool)
    assert isinstance(d["has_under"], bool)
    assert isinstance(d["has_temp_lines"], bool)
    assert isinstance(d["temp_lines_n"], int)
    assert isinstance(d["lines"], list)


@pytest.mark.asyncio
async def test_pick_commit_idempotent_shape(client, session: AsyncSession):
    item_id = await pick_any_item_id(session)
    order_id = await ensure_pickable_order(session, warehouse_id=WAREHOUSE_ID)

    task = await create_pick_task_from_order(client, warehouse_id=WAREHOUSE_ID, order_id=order_id)
    task_id = int(task["id"])

    # 终态合同：REQUIRED 必须 batch_code
    batch_code = "UT-PICK-SHAPE-BATCH"
    _ = await scan_pick(client, task_id=task_id, item_id=item_id, qty=1, batch_code=batch_code)

    # ✅ commit 需要真实库存，否则会 409 insufficient_stock
    now = datetime.now(UTC)
    stock = StockService()
    await stock.adjust(
        session=session,
        warehouse_id=int(WAREHOUSE_ID),
        item_id=int(item_id),
        delta=10,
        reason="RECEIPT",
        ref=f"UT:PICK:SHAPE:SEED:{task_id}",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=now.date(),
        expiry_date=None,
        trace_id="T-UT-SEED",
        meta={"sub_reason": "UT_PICK_SHAPE_SEED"},
    )
    await session.commit()

    r1 = await commit_pick_task(
        client,
        task_id=task_id,
        platform=str(PLATFORM).upper(),
        shop_id=str(SHOP_ID),
        handoff_code=None,
        trace_id=str(task.get("ref") or f"PICKTASK:{task_id}"),
        allow_diff=True,
    )
    assert r1.status_code == 200, r1.text
    a = r1.json()
    _assert_commit_ok_shape(a)
    assert a["idempotent"] is False

    r2 = await commit_pick_task(
        client,
        task_id=task_id,
        platform=str(PLATFORM).upper(),
        shop_id=str(SHOP_ID),
        handoff_code=None,
        trace_id=str(task.get("ref") or f"PICKTASK:{task_id}"),
        allow_diff=True,
    )
    assert r2.status_code == 200, r2.text
    b = r2.json()
    _assert_commit_ok_shape(b)
    assert b["idempotent"] is True

    assert set(a.keys()) == set(b.keys())
    assert set(a["diff"].keys()) == set(b["diff"].keys())
