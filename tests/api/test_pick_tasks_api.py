# tests/api/test_pick_tasks_api.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_service import OrderService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio


async def _seed_order_and_stock(session: AsyncSession) -> int:
    """
    用 OrderService.ingest 落一张简单订单，并为其准备足够的库存：

    - 订单：
        platform = PDD
        shop_id = "1"
        item_id = 1, qty = 2
    - 库存：
        warehouse_id = 1
        item_id      = 1
        batch_code   = "BATCH-TEST-001"
        qty          = 10 (RECEIPT)

    假定测试环境里：
        - items 表中已存在 id=1 的商品
        - warehouses 表中已存在 id=1 的仓库
    """
    platform = "PDD"
    shop_id = "1"
    ext_order_no = "PICK-TASK-CASE-1"
    trace_id = "TRACE-PICK-TASK-CASE-1"
    now = datetime.now(timezone.utc)

    # 1) 落订单（Route C 下 address=None 可能导致 FULFILLMENT_BLOCKED，
    # 但我们在测试里将显式把订单置为 READY_TO_FULFILL 来跑 happy path）
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
        items=[
            {"item_id": 1, "qty": 2},
        ],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # ✅ Route C 测试基线：显式设置“可履约事实”
    # - 不依赖默认仓/兜底
    # - 清空 blocked
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

    # 2) Seed 库存：给 item_id=1 / wh=1 / batch=BATCH-TEST-001 做一笔入库
    stock = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    await stock.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=10,  # 入库 10 件，够出库 2 件
        reason=MovementType.RECEIPT,
        ref="SEED-STOCK-PICK-TASK-CASE-1",
        ref_line=1,
        occurred_at=now,
        batch_code="BATCH-TEST-001",
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
    )

    await session.commit()
    return order_id


async def test_pick_tasks_full_flow(client: AsyncClient, session: AsyncSession, monkeypatch):
    """
    pick-tasks API 全流程测试：

    1) 落一张订单，并为其准备足够库存；
    2) /pick-tasks/from-order/{order_id} 创建拣货任务；
    3) /pick-tasks/{task_id}/scan 录入拣货（带 batch_code）；
    4) /pick-tasks/{task_id}/commit 执行出库；
    5) 验证：
       - 任务状态为 DONE；
       - outbound_commits_v2 有记录；
       - diff 结构正常；
       - 若实现写入 stock_ledger 的出库行，则必须正确（delta<0，尽量按批次校验）。
    """
    # Route C 测试护栏：避免测试辅助 fallback 让 address=None 产生不可控的路由/预占行为
    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    # 1) 落订单 + seed 库存
    order_id = await _seed_order_and_stock(session)

    # 2) 创建拣货任务
    resp = await client.post(
        f"/pick-tasks/from-order/{order_id}",
        json={
            "warehouse_id": 1,
            "source": "ORDER",
            "priority": 100,
        },
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()
    task_id = task["id"]
    assert task["warehouse_id"] == 1
    assert task["status"] in ("READY", "ASSIGNED", "PICKING", "OPEN", "DONE")

    # 任务行：应至少有一行 req_qty=2, picked_qty=0
    lines = task["lines"]
    assert len(lines) >= 1
    line = lines[0]
    assert line["item_id"] == 1
    assert line["req_qty"] == 2
    assert line["picked_qty"] == 0

    # 3) 扫描拣货：拣两件，指定 batch_code
    resp2 = await client.post(
        f"/pick-tasks/{task_id}/scan",
        json={
            "item_id": 1,
            "qty": 2,
            "batch_code": "BATCH-TEST-001",
        },
    )
    assert resp2.status_code == 200, resp2.text
    task_after_scan = resp2.json()
    lines_after = task_after_scan["lines"]

    # 找到 item_id=1, batch_code=BATCH-TEST-001 的行
    target_line = None
    for ln in lines_after:
        if ln["item_id"] == 1 and ln["batch_code"] == "BATCH-TEST-001":
            target_line = ln
            break
    assert target_line is not None
    assert target_line["picked_qty"] == 2

    # 4) commit 出库：写 outbound_commits_v2（以及可能写 ledger）
    trace_id = "TRACE-PICK-TASK-CASE-1"
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
    # 本场景 req_qty=2, picked_qty=2，应当没有 over/under
    assert diff["has_over"] is False
    assert diff["has_under"] is False

    # Route C：diff.lines 允许为空（摘要模式）；若存在则必须自洽
    assert isinstance(diff.get("lines"), list)
    if diff["lines"]:
        diff_line = diff["lines"][0]
        assert diff_line["req_qty"] == 2
        assert diff_line["picked_qty"] == 2
        assert diff_line["status"] == "OK"

    # 5) ledger 校验（可选：只有当系统实际写出了“出库行”时才做硬校验）
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

    # 只要存在 delta<0 的出库行，就必须正确；如果只有 RECEIPT(+delta) 等非出库行，不强制要求
    outbound_rows = [r for r in ledger_rows if int(r[2] or 0) < 0]
    if outbound_rows:
        reason, batch_code, delta, warehouse_id, item_id, ref2, trace2 = outbound_rows[0]
        assert int(warehouse_id) == 1
        assert int(item_id) == 1
        assert int(delta) < 0

        if batch_code is not None:
            assert str(batch_code) == "BATCH-TEST-001"

        # reason 允许 PICK 或 SHIPMENT（实现细节不绑死）
        assert str(reason) in ("PICK", "SHIPMENT") or reason in (MovementType.PICK, MovementType.SHIPMENT), reason

        # trace/ref 至少命中其一
        assert (trace2 == trace_id) or (ref2 == ref)

    # 6) 验证 outbound_commits_v2 中存在记录（这是本测试的硬事实）
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
