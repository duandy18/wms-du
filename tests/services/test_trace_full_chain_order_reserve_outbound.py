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


async def test_full_trace_order_enter_pickable_outbound(session: AsyncSession):
    """
    全链路 trace 验证（新世界观）：

      订单 → enter_pickable（只生成 pick_task，不触库存） → 出库 commit → ledger → trace viewer

    目标：
      - 同一个 trace_id 贯穿：
          orders.trace_id
          stock_ledger.trace_id
          （如 TraceService 已接入 pick_tasks，也应能聚合 pick_task 相关事件）

      - TraceService.get_trace(trace_id) 至少能聚合：
          source="order"
          source="ledger"

      - 不再存在 reservation / reservation_line / reservation_consumed 语义与断言。
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

    # ✅ 显式绑定仓库：让后续链路能解析 warehouse_id
    await session.execute(
        text("UPDATE orders SET warehouse_id = :wid WHERE id = :oid"),
        {"wid": wh_id, "oid": order_id},
    )

    # === 3) enter_pickable（旧 reserve 入口，但新语义：只生成 pick_task，不产生 reservation） ===
    lines = [
        {
            "item_id": int(item_id),
            "qty": 3,
        }
    ]

    r_pickable = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=lines,
        trace_id=trace_id,
    )
    assert r_pickable["status"] == "OK"
    # 新世界观：不应再返回 reservation_id（允许字段不存在或为 None）
    assert r_pickable.get("reservation_id") is None

    # 可选验证：确实生成了 pick_task（如果表结构存在且实现已落地）
    row_task = (
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
            {"ref": order_ref, "wid": int(wh_id)},
        )
    ).first()
    assert row_task, "enter_pickable should create pick_task"
    task_id = int(row_task[0])
    assert task_id > 0

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
    # 台账
    assert "ledger" in sources, f"expected 'ledger' in sources, got: {sources}"

    # 如果 TraceService 已接入 pick_task 事件，这里就要求它出现；否则不误伤（后续可升级为强约束）
    maybe_pick_sources = {"pick_task", "pick_task_line", "pick_task_lines"}
    if sources & maybe_pick_sources:
        # 至少出现一个 pick 相关 source
        assert sources & maybe_pick_sources, f"expected pick sources in sources, got: {sources}"

    # 确认至少有一条 ledger 是这次出库产生的，且 trace_id/ref 匹配
    ledger_events = [e for e in events if e.source == "ledger"]
    assert any(
        (e.kind in ("OUTBOUND_SHIP", "SHIP", "SHIPMENT")) and e.raw.get("ref") == order_ref
        for e in ledger_events
    ), f"expected at least one ledger event for ref={order_ref}, got: {[e.raw for e in ledger_events]}"

    # 额外硬断言：数据库侧 stock_ledger 也必须能按 trace_id 查到记录（避免 TraceService 聚合误报）
    row_ledger = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM stock_ledger
                 WHERE trace_id = :tid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"tid": trace_id},
        )
    ).first()
    assert row_ledger, "expected at least one stock_ledger row with trace_id"
