# tests/services/test_order_service.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item

from app.services.order_service import OrderService
from app.services.pick_task_commit_ship import commit_ship
from app.services.pick_task_commit_ship_handoff import expected_handoff_code_from_task_ref

UTC = timezone.utc
pytestmark = pytest.mark.contract


async def _ensure_order_row(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: int,
    trace_id: str,
) -> str:
    plat = platform.upper()
    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                warehouse_id,
                trace_id,
                created_at
            )
            VALUES (
                :p,
                :s,
                :o,
                :w,
                :tid,
                :created_at
            )
            ON CONFLICT (platform, shop_id, ext_order_no) DO NOTHING
            """
        ),
        {
            "p": plat,
            "s": shop_id,
            "o": ext_order_no,
            "w": warehouse_id,
            "tid": trace_id,
            "created_at": now,
        },
    )
    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


@pytest.mark.asyncio
async def test_pick_task_commit_writes_shipment_reason(session: AsyncSession):
    """
    硬防线：通过 pick_task commit 出库写入的 stock_ledger.reason 必须是 SHIPMENT。

    该用例覆盖：
    - enter_pickable（OrderService.reserve）生成 pick_task + pick_task_lines
    - commit_ship 唯一裁决点：扣库存 + 写 ledger + 写 outbound_commits_v2
    """
    wh, item = 1, 3003

    await ensure_wh_loc_item(session, wh=wh, loc=1, item=item)

    # 非批次库存槽位：qty=10
    await session.execute(
        text(
            """
            INSERT INTO stocks(item_id, warehouse_id, batch_id, batch_code, qty)
            VALUES (:item_id, :wid, NULL, NULL, 10)
            ON CONFLICT (item_id, warehouse_id, batch_code_key)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": int(item), "wid": int(wh)},
    )
    await session.flush()

    platform = "TB"
    shop_id = "TEST"

    # ✅ 用例级唯一 ref，避免命中 outbound_commits_v2 幂等短路
    uniq = uuid4().hex[:10]
    ext_order_no = f"UT-LEDGER-REASON-SHIPMENT-{uniq}"
    trace_id = f"TRACE-{ext_order_no}"

    order_ref = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=wh,
        trace_id=trace_id,
    )

    # enter_pickable：生成 pick_task（不触库存）
    r = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": int(item), "qty": 1}],
        trace_id=trace_id,
    )
    assert r.get("status") == "OK"

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM pick_tasks
                 WHERE ref = :ref AND warehouse_id = :wid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": order_ref, "wid": int(wh)},
        )
    ).first()
    assert row, "pick_task not created"
    task_id = int(row[0])

    # picked_qty=req_qty（无 diff）
    await session.execute(
        text(
            """
            UPDATE pick_task_lines
               SET picked_qty = req_qty,
                   updated_at = now()
             WHERE task_id = :tid
            """
        ),
        {"tid": task_id},
    )
    await session.flush()

    handoff = expected_handoff_code_from_task_ref(ref=order_ref)
    assert handoff, "invalid handoff code"

    result = await commit_ship(
        session,
        task_id=task_id,
        platform=platform,
        shop_id=shop_id,
        handoff_code=handoff,
        trace_id=trace_id,
        allow_diff=False,
    )
    assert result.get("status") == "OK"
    assert result.get("idempotent") is False, f"unexpected idempotent short-circuit: {result}"

    await session.flush()

    row2 = (
        await session.execute(
            text(
                """
                SELECT reason, ref, trace_id, delta
                  FROM stock_ledger
                 WHERE ref = :ref
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": order_ref},
        )
    ).first()
    assert row2 is not None, f"no stock_ledger written for ref={order_ref}"

    reason, ref2, trace2, delta = row2
    assert str(ref2) == order_ref
    assert str(reason) == "SHIPMENT"
    assert int(delta) < 0
    if trace2 is not None:
        assert str(trace2) == trace_id
