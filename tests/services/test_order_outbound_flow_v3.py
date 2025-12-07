# tests/services/test_order_outbound_flow_v3.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService

pytestmark = pytest.mark.asyncio

# —— 固定口径：严格贴合既有基线（由 conftest 或迁移预置）——
WAREHOUSE_ID = 1  # 预置 warehouses(id=1,'WH-1')
ITEM_ID = 3003  # 预置 items(3003,...)
BATCH_CODE = "NEAR"  # 预置 stocks(...,'NEAR') = 10
ORDER_NO = "P3-ORDER-001"


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
    # 订单仅用于生成 ref，不改变库存
    return await OrderService.ingest(
        session,
        platform="pdd",
        shop_id="S-01",
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(timezone.utc),
        items=[{"item_id": ITEM_ID, "qty": 3, "sku_id": "SKU-3003", "title": "ITEM-3003"}],
    )


async def _ship_once(session: AsyncSession, qty: int):
    svc = OutboundService()
    return await svc.commit(
        session=session,
        order_id=ORDER_NO,
        lines=[
            {
                "item_id": ITEM_ID,
                "warehouse_id": WAREHOUSE_ID,
                "batch_code": BATCH_CODE,
                "qty": qty,
            }
        ],
        occurred_at=datetime.now(timezone.utc),
        warehouse_code="WH-1",  # 行内已指定 warehouse_id，这里只是形参占位
    )


async def test_outbound_from_baseline_10_to_7(session: AsyncSession):
    # 0) 基线应为 10，且 ledger 无任何记录
    qty0 = await _read_stocks(session)
    assert qty0 == 10, f"baseline stocks must be 10, got {qty0}"
    led0 = await _sum_ledger(session)
    assert led0 == 0, f"baseline ledger must be 0, got {led0}"

    # 1) 建单（不改变库存）
    o = await _ingest_order(session, ORDER_NO)
    assert o["status"] in ("OK", "IDEMPOTENT")

    # 2) 出库 3（仓+批+UTC，强签名）
    await _ship_once(session, 3)

    # 3) 幂等重放：不得重复扣减
    await _ship_once(session, 3)

    # 4) 校验：stocks 从 10 → 7；ledger 总和为 -3；且两者满足 qty0 + ledger = qty_now
    qty_now = await _read_stocks(session)
    led_now = await _sum_ledger(session)
    assert qty_now == 7, f"stocks should be 7 after ship, got {qty_now}"
    assert led_now == -3, f"ledger sum should be -3, got {led_now}"
    assert qty0 + led_now == qty_now, f"qty0({qty0}) + ledger({led_now}) != qty_now({qty_now})"
