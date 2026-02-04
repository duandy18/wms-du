# tests/api/test_pick_tasks_api.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_service import OrderService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio


async def _get_item_has_shelf_life(session: AsyncSession, item_id: int) -> bool:
    row = (
        await session.execute(
            text("SELECT has_shelf_life FROM items WHERE id = :id LIMIT 1"),
            {"id": int(item_id)},
        )
    ).scalar_one_or_none()
    # has_shelf_life is True 才算“批次受控”
    return bool(row is True)


async def _seed_order_and_stock(session: AsyncSession) -> tuple[int, bool, str | None, str]:
    """
    用 OrderService.ingest 落一张简单订单，并为其准备足够的库存：
    - 订单：PDD / shop_id=1 / item_id=1 qty=2
    - 库存：warehouse_id=1 / item_id=1 / qty=10
    """
    platform = "PDD"
    shop_id = "1"

    uniq = uuid4().hex[:10]
    ext_order_no = f"PICK-TASK-CASE-1-{uniq}"
    trace_id = f"TRACE-PICK-TASK-CASE-1-{uniq}"

    now = datetime.now(timezone.utc)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        buyer_name="拣货测试",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[{"item_id": 1, "qty": 2}],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # ✅ Route C 测试基线：显式设置“可履约事实”
    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = :wid,
                   service_warehouse_id = :wid,
                   fulfillment_warehouse_id = :wid,
                   fulfillment_status = 'READY_TO_FULFILL',
                   blocked_reasons = NULL,
                   blocked_detail = NULL
             WHERE id = :oid
            """
        ),
        {"wid": 1, "oid": order_id},
    )

    requires_batch = await _get_item_has_shelf_life(session, 1)
    expected_batch_code: str | None = "BATCH-TEST-001" if requires_batch else None

    stock = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    await stock.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=10,
        reason=MovementType.RECEIPT,
        ref=f"SEED-STOCK-PICK-TASK-CASE-1-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=expected_batch_code,
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
    )

    await session.commit()
    return order_id, requires_batch, expected_batch_code, trace_id


async def test_pick_tasks_full_flow(client: AsyncClient, session: AsyncSession, monkeypatch):
    """
    pick-tasks API 全流程测试（Phase 2：删除确认码）：
      1) 落订单 + seed 库存
      2) from-order 创建 pick_task
      3) scan 写入 picked 事实
      4) commit（不需要 handoff_code）
      5) ledger/outbound_commits_v2 证据存在性
    """
    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    order_id, requires_batch, expected_batch_code, trace_id = await _seed_order_and_stock(session)

    # 2) 创建拣货任务
    resp = await client.post(
        f"/pick-tasks/from-order/{order_id}",
        json={"warehouse_id": 1, "source": "ORDER", "priority": 100},
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()
    task_id = task["id"]
    assert task["warehouse_id"] == 1
    assert task["status"] in ("READY", "ASSIGNED", "PICKING", "OPEN", "DONE")

    lines = task["lines"]
    assert len(lines) >= 1
    line = lines[0]
    assert line["item_id"] == 1
    assert line["req_qty"] == 2
    assert line["picked_qty"] == 0

    # 3) 扫描拣货：拣两件
    scan_payload = {"item_id": 1, "qty": 2}
    if requires_batch:
        scan_payload["batch_code"] = expected_batch_code

    resp2 = await client.post(
        f"/pick-tasks/{task_id}/scan",
        json=scan_payload,
    )
    assert resp2.status_code == 200, resp2.text
    task_after_scan = resp2.json()
    lines_after = task_after_scan["lines"]

    target_line = None
    for ln in lines_after:
        if ln["item_id"] == 1 and ln.get("batch_code") == expected_batch_code:
            target_line = ln
            break
    assert target_line is not None
    assert target_line["picked_qty"] == 2

    # ✅ 4) commit 出库（Phase 2：不再需要 handoff_code）
    resp3 = await client.post(
        f"/pick-tasks/{task_id}/commit",
        json={
            "platform": "PDD",
            "shop_id": "1",
            "trace_id": trace_id,
            "allow_diff": True,
        },
    )
    assert resp3.status_code == 200, resp3.text
    result = resp3.json()

    assert result["status"] == "OK"
    assert result["task_id"] == task_id
    assert result["warehouse_id"] == 1
    assert result["platform"] == "PDD"
    assert result["shop_id"] == "1"
    ref = result["ref"]
    assert ref.startswith("ORD:PDD:1:")

    diff = result["diff"]
    assert diff["task_id"] == task_id
    assert diff["has_over"] is False
    assert diff["has_under"] is False

    assert isinstance(diff.get("lines"), list)
    if diff["lines"]:
        diff_line = diff["lines"][0]
        assert diff_line["req_qty"] == 2
        assert diff_line["picked_qty"] == 2
        assert diff_line["status"] == "OK"

    # 5) ledger 校验（可选）
    res = await session.execute(
        text(
            """
            SELECT
                reason,
                batch_code,
                delta,
                warehouse_id,
                item_id,
                ref,
                trace_id
              FROM stock_ledger
             WHERE warehouse_id = 1
               AND item_id = 1
               AND (trace_id = :trace_id OR ref = :ref)
             ORDER BY id DESC
             LIMIT 50
            """
        ),
        {"trace_id": trace_id, "ref": ref},
    )
    ledger_rows = res.fetchall()

    outbound_rows = [r for r in ledger_rows if int(r[2] or 0) < 0]
    if outbound_rows:
        reason, batch_code, delta, warehouse_id, item_id, ref2, trace2 = outbound_rows[0]
        assert int(warehouse_id) == 1
        assert int(item_id) == 1
        assert int(delta) < 0

        if requires_batch:
            assert batch_code is not None
            assert str(batch_code) == str(expected_batch_code)
        else:
            assert batch_code is None

        assert str(reason) in ("PICK", "SHIPMENT") or reason in (MovementType.PICK, MovementType.SHIPMENT), reason
        assert (trace2 == trace_id) or (ref2 == ref)

    # 6) outbound_commits_v2 必须存在
    row2 = (
        await session.execute(
            text(
                """
                SELECT
                    platform,
                    shop_id,
                    ref,
                    state,
                    trace_id
                  FROM outbound_commits_v2
                 WHERE platform = :p
                   AND shop_id  = :s
                   AND ref      = :ref
                 LIMIT 1
                """
            ),
            {"p": "PDD", "s": "1", "ref": ref},
        )
    ).first()
    assert row2 is not None, f"no outbound_commits_v2 row for ref={ref}"
    p2, s2, ref3, state2, trace3 = row2
    assert p2 == "PDD"
    assert s2 == "1"
    assert ref3 == ref
    assert state2 in ("COMPLETED", "COMMITTED")
    assert trace3 in (trace_id, ref)
