# tests/services/pick/test_pick_blueprint_db_evidence_contract.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _outbound_commit_rows(session: AsyncSession, *, platform: str, shop_id: str, ref: str):
    r = await session.execute(
        text(
            """
            SELECT trace_id, state, created_at
              FROM outbound_commits_v2
             WHERE platform = :p
               AND shop_id  = :s
               AND ref      = :r
             ORDER BY created_at DESC
            """
        ),
        {"p": platform.upper(), "s": str(shop_id), "r": str(ref)},
    )
    return r.fetchall()


async def _ledger_rows_by_ref(session: AsyncSession, *, ref: str):
    r = await session.execute(
        text(
            """
            SELECT id, reason, delta, after_qty, trace_id
              FROM stock_ledger
             WHERE ref = :ref
             ORDER BY id ASC
            """
        ),
        {"ref": str(ref)},
    )
    return r.fetchall()


@pytest.mark.asyncio
async def test_blueprint_commit_writes_db_evidence_and_is_idempotent(
    client_like,
    db_session_like_pg: AsyncSession,
) -> None:
    ledger0 = await ledger_count(db_session_like_pg)

    order_id = await ensure_pickable_order(db_session_like_pg, warehouse_id=WAREHOUSE_ID)
    task = await create_pick_task_from_order(client_like, warehouse_id=WAREHOUSE_ID, order_id=order_id)
    task_id = int(task["id"])
    task = await get_pick_task(client_like, task_id=task_id)

    ref = get_task_ref(task)
    handoff_code = build_handoff_code(ref)

    lines = task.get("lines") or []
    assert isinstance(lines, list) and len(lines) >= 1, f"pick_task has no lines: {task}"
    first = lines[0]
    item_id = int(first.get("item_id") or 0)
    assert item_id > 0

    await scan_pick(client_like, task_id=task_id, item_id=item_id, qty=1, batch_code=first.get("batch_code"))

    # 1) 首次 commit：必须写台账 + 写 outbound_commits_v2
    trace_id = "T-UT-DB-1"
    r1 = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id=trace_id,
        allow_diff=True,
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1.get("status") == "OK"
    assert bool(body1.get("idempotent")) is False
    assert body1.get("trace_id") == trace_id

    ledger1 = await ledger_count(db_session_like_pg)
    assert ledger1 >= ledger0 + 1

    # outbound_commits_v2 证据
    out_rows = await _outbound_commit_rows(db_session_like_pg, platform=PLATFORM, shop_id=SHOP_ID, ref=ref)
    assert len(out_rows) == 1, {"outbound_commits_v2_rows": out_rows}
    assert str(out_rows[0][0]) == trace_id

    # stock_ledger 证据（必须有负 delta）
    led_rows = await _ledger_rows_by_ref(db_session_like_pg, ref=ref)
    assert led_rows, "expected stock_ledger rows for ref"
    assert any(int(r[2]) < 0 for r in led_rows), {"ledger_rows": led_rows}
    assert any((r[4] or "") == trace_id for r in led_rows), {"ledger_rows": led_rows}

    # 2) 重放 commit：必须幂等，不重复写 outbound_commits_v2，不重复写台账
    ledger_before_replay = await ledger_count(db_session_like_pg)
    out_before_replay = await _outbound_commit_rows(db_session_like_pg, platform=PLATFORM, shop_id=SHOP_ID, ref=ref)

    r2 = await commit_pick_task(
        client_like,
        task_id=task_id,
        platform=PLATFORM,
        shop_id=SHOP_ID,
        handoff_code=handoff_code,
        trace_id=trace_id,
        allow_diff=True,
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("status") == "OK"
    assert bool(body2.get("idempotent")) is True
    assert body2.get("trace_id") == trace_id

    ledger_after_replay = await ledger_count(db_session_like_pg)
    out_after_replay = await _outbound_commit_rows(db_session_like_pg, platform=PLATFORM, shop_id=SHOP_ID, ref=ref)

    assert ledger_after_replay == ledger_before_replay, {
        "msg": "idempotent replay must not write additional stock_ledger rows",
        "before": ledger_before_replay,
        "after": ledger_after_replay,
    }
    assert out_after_replay == out_before_replay, {
        "msg": "idempotent replay must not create additional outbound_commits_v2 rows",
        "before": out_before_replay,
        "after": out_after_replay,
    }
