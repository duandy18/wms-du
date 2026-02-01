# tests/services/test_order_outbound_flow_v3.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService

pytestmark = pytest.mark.asyncio

WAREHOUSE_ID = 1
ITEM_ID = 3003
# 强护栏口径：非批次商品走 NULL 槽位
BATCH_CODE: str | None = None
ORDER_NO = "P3-ORDER-001"


async def _read_stocks(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE item_id=:i AND warehouse_id=:w AND batch_code IS NOT DISTINCT FROM :b
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
            WHERE item_id=:i AND warehouse_id=:w AND batch_code IS NOT DISTINCT FROM :b
            """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
    )
    return int(val.scalar() or 0)


async def _ensure_store_route_to_wh1(session: AsyncSession, *, platform: str, shop_id: str, province: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (platform, shop_id, name)
            VALUES (:p,:s,:n)
            ON CONFLICT (platform, shop_id) DO NOTHING
            """
        ),
        {"p": platform.upper(), "s": shop_id, "n": f"UT-{platform.upper()}-{shop_id}"},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": platform.upper(), "s": shop_id},
    )
    store_id = int(row.scalar_one())

    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            ON CONFLICT (store_id, warehouse_id) DO NOTHING
            """
        ),
        {"sid": store_id, "wid": WAREHOUSE_ID},
    )
    await session.execute(
        text("DELETE FROM store_province_routes WHERE store_id=:sid AND province=:prov"),
        {"sid": store_id, "prov": province},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_province_routes (store_id, province, warehouse_id, priority, active)
            VALUES (:sid, :prov, :wid, 10, TRUE)
            """
        ),
        {"sid": store_id, "prov": province, "wid": WAREHOUSE_ID},
    )


async def _ingest_order(session: AsyncSession, ext_order_no: str):
    province = "UT-P3"
    await _ensure_store_route_to_wh1(session, platform="PDD", shop_id="S-01", province=province)
    return await OrderService.ingest(
        session,
        platform="PDD",
        shop_id="S-01",
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(timezone.utc),
        items=[{"item_id": ITEM_ID, "qty": 3, "sku_id": "SKU-3003", "title": "ITEM-3003"}],
        address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
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
        warehouse_code="WH-1",
    )


async def test_outbound_from_baseline_10_to_7(session: AsyncSession):
    qty0 = await _read_stocks(session)
    assert qty0 == 10, f"baseline stocks must be 10, got {qty0}"
    led0 = await _sum_ledger(session)
    assert led0 == 0, f"baseline ledger must be 0, got {led0}"

    o = await _ingest_order(session, ORDER_NO)
    assert o["status"] in ("OK", "IDEMPOTENT"), f"ingest returned: {o}"

    await _ship_once(session, 3)
    await _ship_once(session, 3)

    qty_now = await _read_stocks(session)
    led_now = await _sum_ledger(session)
    assert qty_now == 7, f"stocks should be 7 after ship, got {qty_now}"
    assert led_now == -3, f"ledger sum should be -3, got {led_now}"
    assert qty0 + led_now == qty_now, f"qty0({qty0}) + ledger({led_now}) != qty_now({qty_now})"
