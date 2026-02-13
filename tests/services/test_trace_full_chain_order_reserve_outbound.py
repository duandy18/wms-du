from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService
from app.services.stock_service import StockService
from app.services.trace_service import TraceService

pytestmark = pytest.mark.asyncio

UTC = timezone.utc


async def test_full_trace_order_outbound(session: AsyncSession):
    """
    全链路 trace 验证（当前主线）：

      订单 → 出库 commit → ledger → trace viewer

    目标：
      - 同一个 trace_id 贯穿：
          orders.trace_id
          stock_ledger.trace_id

      - TraceService.get_trace(trace_id) 至少能聚合：
          source="order"
          source="ledger"
          source="outbound"（如实现已接入）
    """
    # === 0) 准备基础数据：选一个已有 item + 仓库 ===
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    item_id = row.scalar_one()
    assert item_id is not None

    platform = "PDD"
    shop_id = "1"
    ext_order_no = "TRACE-E2E-1"
    trace_id = "TRACE-E2E-1"

    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wh_id = int(row.scalar_one())

    stock_svc = StockService()
    now = datetime.now(UTC)
    batch_code = "B-TRACE-E2E-1"

    # === 1) 预先做一次入库：给这个 item/仓/批次准备库存 ===
    await stock_svc.adjust(
        session=session,
        scope="PROD",
        item_id=int(item_id),
        warehouse_id=wh_id,
        delta=10,
        reason="UT_TRACE_SEED_INBOUND",
        ref="UT-TRACE-SEED",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        trace_id=trace_id,
    )

    # === 2) 建订单 ===
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    r_order = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        buyer_name="Cat Lover",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[
            {
                "item_id": int(item_id),
                "sku_id": "SKU-TRACE-1",
                "title": "UT Trace Product",
                "qty": 3,
                "price": 100,
                "discount": 0,
                "amount": 300,
            }
        ],
        address={
            "receiver_name": "Cat Lover",
            "receiver_phone": "13800000000",
            "province": "UT",
            "city": "TraceCity",
            "district": "TraceDist",
            "detail": "Trace Street 1",
            "zipcode": "000000",
        },
        extras={"ut": "trace"},
        trace_id=trace_id,
    )
    assert r_order["status"] in ("OK", "IDEMPOTENT")
    order_id = r_order["id"]
    assert order_id is not None

    # 显式绑定执行仓（测试用，避免依赖外部路由策略）
    # 新世界观：执行仓事实写入 order_fulfillment.actual_warehouse_id
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
              :wid,
              :wid,
              'READY_TO_FULFILL',
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                   actual_warehouse_id  = EXCLUDED.actual_warehouse_id,
                   fulfillment_status   = EXCLUDED.fulfillment_status,
                   blocked_reasons      = NULL,
                   updated_at           = now()
            """
        ),
        {"wid": wh_id, "oid": int(order_id)},
    )

    # === 3) 出库（OutboundService.commit）→ ledger.trace_id ===
    outbound_svc = OutboundService(stock_svc)

    r_outbound = await outbound_svc.commit(
        session=session,
        order_id=order_ref,
        lines=[
            {
                "item_id": int(item_id),
                "batch_code": batch_code,
                "qty": 3,
                "warehouse_id": wh_id,
            }
        ],
        occurred_at=now,
        trace_id=trace_id,
    )
    assert r_outbound["status"] == "OK"
    assert r_outbound["total_qty"] == 3

    # === 4) Trace 聚合 ===
    trace_svc = TraceService(session)
    result = await trace_svc.get_trace(trace_id)

    events = result.events
    assert events, "trace events should not be empty"

    sources = {e.source for e in events}
    assert "order" in sources
    assert "ledger" in sources

    # outbound source 如存在则校验（不把它当强依赖）
    if "outbound" in sources:
        assert any(e.source == "outbound" for e in events)

    ledger_events = [e for e in events if e.source == "ledger"]
    assert any(
        (e.kind in ("OUTBOUND_SHIP", "SHIP", "SHIPMENT")) and e.raw.get("ref") == order_ref
        for e in ledger_events
    )

    row_ledger = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM stock_ledger
                 WHERE scope='PROD'
                   AND trace_id = :tid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"tid": trace_id},
        )
    ).first()
    assert row_ledger
