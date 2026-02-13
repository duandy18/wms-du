# tests/api/test_pick_tasks_from_order_contract.py
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
    """
    合同测试的最小数据准备：
    - 造一单
    - 造库存
    - 订单状态设为可拣货（避免 fulfillment_status 阻塞）
    """
    platform = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext_order_no = f"UT-PICK-FROM-ORDER-{uniq}"
    trace_id = f"TRACE-{ext_order_no}"
    now = datetime.now(timezone.utc)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        buyer_name="拣货 from-order 合同测试",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[{"item_id": 1, "qty": 1}],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # ✅ 可拣货护栏：避免因 blocked 导致 from-order 无法创建
    # 新世界观：orders 不再有 fulfillment_status / blocked_* 列，统一写 order_fulfillment
    # 注意：本合同不依赖 orders.warehouse_id/service_warehouse_id 来解析执行仓
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
    batch_code = "BATCH-TEST-FROM-ORDER" if requires_batch else None

    stock = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    await stock.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=10,
        reason=MovementType.RECEIPT,
        ref=f"SEED-STOCK-FROM-ORDER-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
    )

    await session.commit()
    return order_id


async def test_pick_tasks_from_order_contract(
    client: AsyncClient,
    session: AsyncSession,
):
    order_id = await _seed_order_and_stock(session)

    # 1) 手工主线：warehouse_id 必须显式（走 manual-from-order）
    r0 = await client.post(
        f"/pick-tasks/manual-from-order/{order_id}",
        json={"source": "ORDER", "priority": 100},
    )
    assert r0.status_code == 422, r0.text

    # 2) 自动主线：from-order 不要求 warehouse_id（执行仓由店铺默认仓解析）
    r_auto_main = await client.post(
        f"/pick-tasks/from-order/{order_id}",
        json={"source": "ORDER", "priority": 100},
    )
    assert r_auto_main.status_code == 200, r_auto_main.text
    task_auto = r_auto_main.json()
    task_auto_id = int(task_auto["id"])

    r_auto_get = await client.get(f"/pick-tasks/{task_auto_id}")
    assert r_auto_get.status_code == 200, r_auto_get.text
    auto_body = r_auto_get.json()
    assert auto_body.get("print_job") is None, auto_body

    # 3) 自动化入口：明确禁用
    r_auto_disabled = await client.post(
        f"/pick-tasks/ensure-from-order/{order_id}",
        json={},
    )
    assert r_auto_disabled.status_code == 422, r_auto_disabled.text

    # 4) 手工入口：显式 warehouse_id 正确创建（不自动打印）
    r1 = await client.post(
        f"/pick-tasks/manual-from-order/{order_id}",
        json={"warehouse_id": 1, "source": "ORDER", "priority": 100},
    )
    assert r1.status_code == 200, r1.text
    task = r1.json()
    task_id = int(task["id"])

    r2 = await client.get(f"/pick-tasks/{task_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("print_job") is None, body

    # 5) 手工触发打印（幂等）
    r3 = await client.post(
        f"/pick-tasks/{task_id}/print-pick-list",
        json={"order_id": int(order_id)},
    )
    assert r3.status_code == 200, r3.text
    pj1 = r3.json().get("print_job")
    assert isinstance(pj1, dict), r3.json()
    pj_id = int(pj1.get("id") or 0)
    assert pj_id > 0

    r4 = await client.post(
        f"/pick-tasks/{task_id}/print-pick-list",
        json={"order_id": int(order_id)},
    )
    assert r4.status_code == 200, r4.text
    pj2 = r4.json().get("print_job")
    assert isinstance(pj2, dict), r4.json()
    assert int(pj2.get("id") or 0) == pj_id
