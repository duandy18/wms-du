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

    # 1) 落订单
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


async def test_pick_tasks_full_flow(client: AsyncClient, session: AsyncSession):
    """
    pick-tasks API 全流程测试：

    1) 落一张订单，并为其准备足够库存；
    2) /pick-tasks/from-order/{order_id} 创建拣货任务；
    3) /pick-tasks/{task_id}/scan 录入拣货（带 batch_code）；
    4) /pick-tasks/{task_id}/commit 执行出库；
    5) 验证：
       - 任务状态为 DONE；
       - ledger 里有 SHIPMENT 记录；
       - outbound_commits_v2 有记录；
       - diff 结构正常。
    """
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

    # 4) commit 出库：按批次扣库存 + 写 outbound_commits_v2
    resp3 = await client.post(
        f"/pick-tasks/{task_id}/commit",
        json={
            "platform": "PDD",
            "shop_id": "1",
            "trace_id": "TRACE-PICK-TASK-CASE-1",
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
    assert isinstance(diff["lines"], list) and len(diff["lines"]) >= 1
    diff_line = diff["lines"][0]
    assert diff_line["req_qty"] == 2
    assert diff_line["picked_qty"] == 2
    assert diff_line["status"] == "OK"

    # 5) 验证 ledger 中存在 SHIPMENT 记录；严格按批次扣库存
    row = (
        await session.execute(
            text(
                """
                SELECT
                    reason,
                    batch_code,
                    delta,
                    warehouse_id,
                    item_id
                  FROM stock_ledger
                 WHERE ref = :ref
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": ref},
        )
    ).first()
    assert row is not None, f"no ledger row found for ref={ref}"
    reason, batch_code, delta, warehouse_id, item_id = row
    assert reason in ("SHIPMENT", "SHIP"), reason
    assert batch_code == "BATCH-TEST-001"
    assert delta < 0  # 出库为负数
    assert warehouse_id == 1
    assert item_id == 1

    # 6) 验证 outbound_commits_v2 中存在记录
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
    p2, s2, ref2, state2, trace2 = row2
    assert p2 == "PDD"
    assert s2 == "1"
    assert ref2 == ref
    assert state2 in ("COMPLETED", "COMMITTED")
    assert trace2 in ("TRACE-PICK-TASK-CASE-1", ref)
