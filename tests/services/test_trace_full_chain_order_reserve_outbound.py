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


async def test_full_trace_order_reserve_outbound(session: AsyncSession):
    """
    全链路 trace 验证：

      订单 → 渠道占用 → 出库 → ledger → trace viewer

    目标：
      - 同一个 trace_id 贯穿：
          orders.trace_id
          reservations.trace_id
          stock_ledger.trace_id
      - TraceService.get_trace(trace_id) 能同时聚合：
          source="order"
          source="reservation"
          source="reservation_line"
          source="ledger"
          source="reservation_consumed"  (Ship v3)
      - Ship v3：出库后自动消费对应预占（reservation_lines.consumed_qty）
    """
    # === 0) 准备基础数据：选一个已有 item + 仓库 ===
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    item_id = row.scalar_one()
    assert item_id is not None

    platform = "PDD"
    shop_id = "1"  # 复用测试基线里的店铺，避免破坏现有假数据
    ext_order_no = "TRACE-E2E-1"
    trace_id = "TRACE-E2E-1"

    # 使用测试基线中的默认仓：从 warehouses 表中取第一个
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wh_id = int(row.scalar_one())

    # === 1) 预先做一次入库：给这个 item/仓/批次准备库存 ===
    stock_svc = StockService()
    now = datetime.now(UTC)
    batch_code = "B-TRACE-E2E-1"

    await stock_svc.adjust(
        session=session,
        item_id=int(item_id),
        warehouse_id=wh_id,
        delta=10,  # 入库 +10
        reason="UT_TRACE_SEED_INBOUND",
        ref="UT-TRACE-SEED",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        trace_id=trace_id,  # 这条入库台账也挂在同一个 trace 上
    )

    # === 2) 建订单（OrderService.ingest），写 orders.trace_id ===
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

    # ✅ 显式绑定仓库：让 Golden Flow 的 OrderReserveFlow 能解析 warehouse_id
    await session.execute(
        text("UPDATE orders SET warehouse_id = :wid WHERE id = :oid"),
        {"wid": wh_id, "oid": order_id},
    )

    # === 3) 渠道占用（OrderService.reserve）→ reservations.trace_id ===
    lines = [
        {
            "item_id": int(item_id),
            "qty": 3,
        }
    ]

    r_reserve = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=lines,
        trace_id=trace_id,
    )
    assert r_reserve["status"] == "OK"
    reservation_id = r_reserve.get("reservation_id")
    assert reservation_id is not None

    # === 4) 出库（OutboundService.commit）→ ledger.trace_id ===
    outbound_svc = OutboundService(stock_svc)

    r_outbound = await outbound_svc.commit(
        session=session,
        order_id=order_ref,  # 这里作为 ledger.ref 使用
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

    # === 5) 使用 TraceService 聚合全链路 ===
    trace_svc = TraceService(session)
    result = await trace_svc.get_trace(trace_id)

    events = result.events
    assert events, "trace events should not be empty"

    sources = {e.source for e in events}

    # 订单事件
    assert "order" in sources, f"expected 'order' in sources, got: {sources}"
    # 占用 + 明细
    assert "reservation" in sources, f"expected 'reservation' in sources, got: {sources}"
    assert "reservation_line" in sources, f"expected 'reservation_line' in sources, got: {sources}"
    # 台账
    assert "ledger" in sources, f"expected 'ledger' in sources, got: {sources}"
    # Ship v3：预占被消耗的事件应存在
    assert (
        "reservation_consumed" in sources
    ), f"expected 'reservation_consumed' in sources, got: {sources}"

    # 确认至少有一条 ledger 是这次出库（OUTBOUND_SHIP）产生的，且 trace_id 匹配
    ledger_events = [e for e in events if e.source == "ledger"]
    assert any(
        (e.kind in ("OUTBOUND_SHIP", "SHIP")) and e.raw.get("ref") == order_ref
        for e in ledger_events
    ), f"expected at least one ledger event for ref={order_ref}, got: {[e.raw for e in ledger_events]}"

    # reservations 侧也要挂 trace_id（间接验证：能通过 trace_id 抓到 reservation）
    res_events = [e for e in events if e.source == "reservation"]
    assert res_events, "expected at least one reservation event in trace"
    assert all(
        e.raw.get("trace_id") == trace_id for e in res_events
    ), f"reservation events trace_id mismatch: {[e.raw for e in res_events]}"

    # === 6) Ship v3 自动 consume 预占：reservation_lines.consumed_qty 应等于 qty ===
    rows = await session.execute(
        text(
            """
            SELECT qty, consumed_qty
              FROM reservation_lines
             WHERE reservation_id = :rid
            """
        ),
        {"rid": reservation_id},
    )
    row_lines = rows.fetchall()
    assert row_lines, "expected at least one reservation_line"

    total_qty = sum(int(q[0]) for q in row_lines)
    total_consumed = sum(int(q[1] or 0) for q in row_lines)

    # 本用例中 reserve qty = 3，出库 qty = 3 → 全部 consumed
    assert total_qty == 3
    assert total_consumed == 3

    # === 7) 再从 TraceResult 角度检查 reservation_consumption 汇总 ===
    consumption = result.reservation_consumption
    # 只检查当前 reservation，避免误伤其它 trace 数据
    assert reservation_id in consumption
    per_item = consumption[reservation_id]
    assert int(item_id) in per_item
    assert per_item[int(item_id)]["qty"] == 3
    assert per_item[int(item_id)]["consumed"] == 3
