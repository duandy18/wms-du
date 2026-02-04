# tests/api/test_pick_tasks_print_job_contract.py
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
    return bool(row is True)


async def _seed_order_and_stock(session: AsyncSession) -> int:
    platform = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext_order_no = f"UT-PICK-PRINTJOB-{uniq}"
    trace_id = f"TRACE-{ext_order_no}"
    now = datetime.now(timezone.utc)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        buyer_name="拣货打印合同测试",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[{"item_id": 1, "qty": 2}],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # 可拣货护栏：避免订单被 BLOCKED 误伤测试主线
    # 新世界观：orders 不再有 fulfillment_status / blocked_* 列，统一写 order_fulfillment（blocked 只保留 reasons）
    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
              order_id,
              planned_warehouse_id,
              actual_warehouse_id,
              fulfillment_status,
              blocked_reasons,
              updated_at
            )
            VALUES (
              :oid,
              NULL,
              1,
              'READY_TO_FULFILL',
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = now()
            """
        ),
        {"oid": int(order_id)},
    )

    requires_batch = await _get_item_has_shelf_life(session, 1)
    batch_code = "BATCH-TEST-PRINTJOB" if requires_batch else None

    stock = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    await stock.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=10,
        reason=MovementType.RECEIPT,
        ref=f"SEED-STOCK-PRINTJOB-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
    )

    await session.commit()
    return order_id


async def test_pick_task_get_includes_print_job_summary(
    client: AsyncClient,
    session: AsyncSession,
):
    order_id = await _seed_order_and_stock(session)

    # 创建拣货任务（手工主线：必须显式 warehouse_id；只创建任务，不自动 enqueue 打印）
    r1 = await client.post(
        f"/pick-tasks/manual-from-order/{order_id}",
        json={"warehouse_id": 1, "source": "ORDER", "priority": 100},
    )
    assert r1.status_code == 200, r1.text
    task = r1.json()
    task_id = int(task["id"])

    # GET 任务详情：创建后不应自动带 print_job（自动化已剥离）
    r2 = await client.get(f"/pick-tasks/{task_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()

    pj0 = body.get("print_job")
    assert pj0 is None, body

    # 手工触发打印：显式 enqueue pick_list print_job（幂等）
    r3 = await client.post(
        f"/pick-tasks/{task_id}/print-pick-list",
        json={"order_id": int(order_id)},
    )
    assert r3.status_code == 200, r3.text

    # 再 GET：必须带 print_job（可观测闭环）
    r4 = await client.get(f"/pick-tasks/{task_id}")
    assert r4.status_code == 200, r4.text
    body2 = r4.json()

    pj = body2.get("print_job")
    assert isinstance(pj, dict), body2
    assert pj.get("kind") == "pick_list", pj
    assert pj.get("ref_type") == "pick_task", pj
    assert int(pj.get("ref_id") or 0) == task_id, pj
    assert pj.get("status") in ("queued", "printed", "failed"), pj
