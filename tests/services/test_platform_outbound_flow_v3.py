# tests/services/test_platform_outbound_flow_v3.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.platform_events import handle_event_batch

pytestmark = pytest.mark.asyncio

# 与 tests/conftest.py 的基线严格一致
WAREHOUSE_ID = 1
ITEM_ID = 3003
BATCH_CODE = "NEAR"
ORDER_NO = "P3-ORDER-PLATFORM-001"


async def _read_stocks(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE item_id=:i AND warehouse_id=:w AND batch_code=:b
                LIMIT 1
                """
            ),
            {"i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
        )
    ).first()
    return int(row[0]) if row else 0


async def _sum_ledger(session: AsyncSession) -> int:
    val = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
            FROM stock_ledger
            WHERE item_id=:i AND warehouse_id=:w AND batch_code=:b
            """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
    )
    return int(val.scalar() or 0)


async def _ingest_order(session: AsyncSession, ext_order_no: str):
    # 平台订单仅用于生成 ref，不改变库存
    return await OrderService.ingest(
        session,
        platform="pdd",
        shop_id="S-01",
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(timezone.utc),
        items=[{"item_id": ITEM_ID, "qty": 3, "sku_id": "SKU-3003", "title": "ITEM-3003"}],
    )


async def test_platform_events_outbound_flow(session: AsyncSession):
    # 0) 基线：stocks=10，ledger=0
    qty0 = await _read_stocks(session)
    led0 = await _sum_ledger(session)
    assert qty0 == 10, f"baseline stocks must be 10, got {qty0}"
    assert led0 == 0, f"baseline ledger must be 0, got {led0}"

    # 1) 建单（只为获得 ref）
    o = await _ingest_order(session, ORDER_NO)
    assert o["status"] in ("OK", "IDEMPOTENT")

    # 2) 预约（RESERVE）：不触发库存/台账，仅测试调用契约
    reserve_events = [
        {
            "platform": "pdd",
            "shop_id": "S-01",
            "order_sn": ORDER_NO,
            "status": "PAID",  # → RESERVE
            "lines": [{"item_id": ITEM_ID, "qty": 3}],
        }
    ]
    await handle_event_batch(reserve_events, session=session)

    # 3) 发货（SHIP）：严格“仓+批+UTC”，走 platform_events → OutboundService.commit（新签名）
    ship_events = [
        {
            "platform": "pdd",
            "shop_id": "S-01",
            "order_sn": ORDER_NO,
            "status": "SHIPPED",
            "lines": [
                {
                    "item_id": ITEM_ID,
                    "warehouse_id": WAREHOUSE_ID,
                    "batch_code": BATCH_CODE,
                    "qty": 3,
                }
            ],
        }
    ]
    await handle_event_batch(ship_events, session=session)

    # 4) 幂等重放：不得重复扣减
    await handle_event_batch(ship_events, session=session)

    # 5) 对账：10 - 3 = 7；ledger 合计为 -3；守恒 qty0 + ledger == qty_now
    qty_now = await _read_stocks(session)
    led_now = await _sum_ledger(session)
    assert qty_now == 7, f"stocks should be 7 after ship, got {qty_now}"
    assert led_now == -3, f"ledger sum should be -3, got {led_now}"
    assert qty0 + led_now == qty_now, f"qty0({qty0}) + ledger({led_now}) != qty_now({qty_now})"


async def test_platform_events_cancel_does_not_affect_committed_stock(session: AsyncSession):
    """
    取消占用（CANCEL）不会影响已扣账的库存。
    流程：建单→RESERVE→SHIP（-3）→CANCEL→校验库存仍为 7、台账 -3。
    """
    # 建单
    await _ingest_order(session, ORDER_NO)

    # 基线应为 10 / 0
    assert await _read_stocks(session) == 10
    assert await _sum_ledger(session) == 0

    # RESERVE
    await handle_event_batch(
        [
            {
                "platform": "pdd",
                "shop_id": "S-01",
                "order_sn": ORDER_NO,
                "status": "PAID",
                "lines": [{"item_id": ITEM_ID, "qty": 3}],
            }
        ],
        session=session,
    )

    # SHIP（-3）
    await handle_event_batch(
        [
            {
                "platform": "pdd",
                "shop_id": "S-01",
                "order_sn": ORDER_NO,
                "status": "SHIPPED",
                "lines": [
                    {
                        "item_id": ITEM_ID,
                        "warehouse_id": WAREHOUSE_ID,
                        "batch_code": BATCH_CODE,
                        "qty": 3,
                    }
                ],
            }
        ],
        session=session,
    )

    # CANCEL：不应改动已扣账的库存
    await handle_event_batch(
        [
            {
                "platform": "pdd",
                "shop_id": "S-01",
                "order_sn": ORDER_NO,
                "status": "CANCELED",
                "lines": [{"item_id": ITEM_ID, "qty": 3}],
            }
        ],
        session=session,
    )

    assert await _read_stocks(session) == 7
    assert await _sum_ledger(session) == -3
