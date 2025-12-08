# tests/services/test_outbound_e2e_phase4_success.py
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code, seed_batch_slot

from app.models.enums import MovementType
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService, ShipLine
from app.services.stock_service import StockService

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_ingest_reserve_ship_e2e_phase4_success(db_session_like_pg, monkeypatch):
    """
    Phase 4：在真实 FEFO 库存存在时，验证：

    - ingest：订单被路由到主仓（orders.warehouse_id）
    - reserve：reservations.warehouse_id 与订单仓一致
    - ship：成功出库，committed_lines == 1, total_qty == 5，批次库存归零
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    # 选定 wh/loc/item/batch
    wh = 1
    loc = 101
    item_id = 9001
    batch_code = "FEFO-NEAR"

    # 1) 建域：仓库 / 库位 / 商品
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item_id)
    await session.commit()

    # 2) 用 seed_batch_slot 构造 FEFO 批次库存：item_id 在 wh 上有 qty=5
    await seed_batch_slot(
        session,
        item=item_id,
        loc=loc,
        code=batch_code,
        qty=5,
        days=30,  # 近效期
    )
    await session.commit()

    # 3) 把 S1 绑定到 wh=1（主仓）
    row = await session.execute(
        text(
            """
            SELECT id
              FROM stores
             WHERE platform = :p
               AND shop_id  = :s
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id},
    )
    store_id = row.scalar()
    assert store_id is not None, "store PDD/S1 should exist in seed data"

    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id = :sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            """
        ),
        {"sid": store_id, "wid": wh},
    )
    await session.commit()

    # 4) 路由/预占使用的 ChannelInventoryService：简单 monkeypatch，保证可用量足够
    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id_ = kwargs.get("item_id")
        # 在 wh/item_id 上返回足够可用量，其他组合返回 0
        if warehouse_id == wh and item_id_ == item_id:
            return 100
        return 0

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    # 5) ingest：创建订单
    ext_order_no = "FEFO-SUCC-1"
    trace_id = "TRACE-FEFO-SUCCESS-001"
    occurred_at = datetime.now(UTC)

    ingest_result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=occurred_at,
        buyer_name="张三",
        buyer_phone="13800000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": item_id,
                "sku_id": f"SKU-{item_id}",
                "title": "FEFO 成功测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id=trace_id,
    )

    assert ingest_result["status"] == "OK"
    order_id = ingest_result["id"]
    order_ref = ingest_result["ref"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    order_wh = row.scalar()
    assert order_wh == wh

    # 6) reserve：按同一 ref 建立软占用
    reserve_result = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": item_id, "qty": 5}],
        trace_id=trace_id,
    )
    assert reserve_result["status"] == "OK"

    # reservations.warehouse_id 必须与订单仓一致
    row = await session.execute(
        text(
            """
            SELECT warehouse_id
              FROM reservations
             WHERE platform = :p
               AND shop_id  = :s
               AND ref      = :r
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"p": platform.upper(), "s": shop_id, "r": order_ref},
    )
    res_wh = row.scalar()
    assert res_wh == order_wh == wh

    # 7) ship：构造 ShipLine，指定同一仓 + 批次
    ship_lines = [
        ShipLine(
            item_id=item_id,
            batch_code=batch_code,
            qty=5,
            warehouse_id=wh,
        )
    ]

    svc = OutboundService()
    ship_result = await svc.commit(
        session=session,
        order_id=order_id,
        lines=ship_lines,
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
    )

    # ship 正常返回，并且 1 行成功出库
    assert isinstance(ship_result, dict)
    assert ship_result.get("order_id") == str(order_id)
    assert ship_result.get("status") == "OK"
    assert ship_result.get("committed_lines") == 1

    results = ship_result.get("results") or []
    assert len(results) == 1
    line_res = results[0]
    assert line_res.get("item_id") == item_id
    assert line_res.get("batch_code") == batch_code
    # 不应该有 error，或者 error 为空
    assert not line_res.get("error")

    # 8) 校验 FEFO 库存被正确扣减：该批次库存为 0
    await session.commit()
    remaining = await qty_by_code(session, item=item_id, loc=loc, code=batch_code)
    assert remaining == 0
