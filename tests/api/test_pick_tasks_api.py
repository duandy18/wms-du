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


def _handoff_from_order_ref(order_ref: str) -> str:
    """
    order_ref: ORD:{PLAT}:{shop}:{ext}
    handoff:   WMS:ORDER:v1:{PLAT}:{shop}:{ext}
    """
    if not isinstance(order_ref, str) or not order_ref.startswith("ORD:"):
        raise ValueError(f"invalid order_ref for handoff: {order_ref}")
    parts = order_ref.split(":", 3)
    if len(parts) != 4:
        raise ValueError(f"invalid order_ref parts: {order_ref}")
    _, plat, shop, ext = parts
    plat = (plat or "").upper().strip()
    shop = (shop or "").strip()
    ext = (ext or "").strip()
    if not plat or not shop or not ext:
        raise ValueError(f"invalid order_ref fields: {order_ref}")
    return f"WMS:ORDER:v1:{plat}:{shop}:{ext}"


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

    - 订单：
        platform = PDD
        shop_id = "1"
        item_id = 1, qty = 2
    - 库存：
        warehouse_id = 1
        item_id      = 1
        batch_code   = (has_shelf_life=true ? "BATCH-TEST-001" : NULL)
        qty          = 10 (RECEIPT)

    假定测试环境里：
        - items 表中已存在 id=1 的商品
        - warehouses 表中已存在 id=1 的仓库

    主线 A 合同：
      - has_shelf_life=true：batch_code 必填且非空
      - has_shelf_life IS NOT TRUE：batch_code 必须为 NULL
    """
    platform = "PDD"
    shop_id = "1"

    # ✅ 关键：用例级唯一后缀，避免 ref/任务唯一键被其它测试污染
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

    # 关键：根据 item.has_shelf_life 决定批次语义
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
    pick-tasks API 全流程测试：

    1) 落一张订单，并为其准备足够库存；
    2) /pick-tasks/from-order/{order_id} 创建拣货任务；
    3) /pick-tasks/{task_id}/scan 录入拣货（按 has_shelf_life 决定是否带 batch_code）；
    4) /pick-tasks/{task_id}/commit 执行出库（必须带 handoff_code）；
    5) 验证：
       - 任务状态为 DONE；
       - outbound_commits_v2 有记录；
       - diff 结构正常；
       - 若实现写入 stock_ledger 的出库行，则必须正确（delta<0，尽量按批次校验）。
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

    # ✅ 4) commit 出库：先从 DB 取 task.ref，再生成 handoff_code
    row_ref = (
        await session.execute(
            text("SELECT ref FROM pick_tasks WHERE id = :id LIMIT 1"),
            {"id": int(task_id)},
        )
    ).scalar_one_or_none()
    assert row_ref is not None
    order_ref = str(row_ref)
    handoff_code = _handoff_from_order_ref(order_ref)

    resp3 = await client.post(
        f"/pick-tasks/{task_id}/commit",
        json={
            "platform": "PDD",
            "shop_id": "1",
            "handoff_code": handoff_code,
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

        # 批次商品：尽量按批次校验；非批次：batch_code 可能为 NULL
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
