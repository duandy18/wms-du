# tests/services/test_order_outbound_flow_v3.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio

WAREHOUSE_ID = 1
ITEM_ID = 3003
BATCH_CODE: str | None = None
ORDER_NO = "P3-ORDER-001"


async def _read_qty_lot(session: AsyncSession) -> int:
    val = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(sl.qty), 0)
              FROM stocks_lot sl
              LEFT JOIN lots lo ON lo.id = sl.lot_id
             WHERE sl.item_id=:i
               AND sl.warehouse_id=:w
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
            """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "c": BATCH_CODE},
    )
    return int(val.scalar_one_or_none() or 0)


async def _sum_ledger(session: AsyncSession) -> int:
    val = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.item_id=:i
               AND l.warehouse_id=:w
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
            """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "c": BATCH_CODE},
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
    order_ref = f"ORD:PDD:S-01:{ORDER_NO}"
    return await svc.commit(
        session=session,
        order_id=order_ref,
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


async def _ensure_seed_to_10(session: AsyncSession) -> None:
    """
    Phase 4E：不再依赖 legacy baseline(stocks)，测试自给自足 seed 到 qty=10（lot-world 余额）。
    """
    # 本用例测试 NONE/internal-lot：局部把 item 改回 NONE
    await session.execute(
        text("UPDATE items SET expiry_policy='NONE'::expiry_policy WHERE id=:i"),
        {"i": int(ITEM_ID)},
    )
    await session.commit()

    svc = StockService()
    before = await _read_qty_lot(session)
    if before >= 10:
        return

    need = 10 - before
    await svc.adjust(
        session=session,
        item_id=ITEM_ID,
        warehouse_id=WAREHOUSE_ID,
        delta=int(need),
        reason=MovementType.INBOUND,
        ref=f"UT-SEED-OUTFLOW-{ITEM_ID}-{WAREHOUSE_ID}-NULL",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
        batch_code=None,
    )
    await session.commit()


async def test_outbound_from_seed_10_to_7(session: AsyncSession):
    await _ensure_seed_to_10(session)

    qty0 = await _read_qty_lot(session)
    assert qty0 == 10, f"seed qty must be 10, got {qty0}"

    # 终态：seed 可能（并且通常应该）写入 stock_ledger，因此不要假设 led0==0
    led0 = await _sum_ledger(session)

    o = await _ingest_order(session, ORDER_NO)
    assert o["status"] in ("OK", "IDEMPOTENT"), f"ingest returned: {o}"

    await _ship_once(session, 3)
    await _ship_once(session, 3)

    qty_now = await _read_qty_lot(session)
    led_now = await _sum_ledger(session)

    assert qty_now == 7, f"qty should be 7 after ship, got {qty_now}"

    # 以 seed 后 ledger 为基线，验证本用例的“净出库效果”为 -3
    delta_led = int(led_now) - int(led0)
    assert delta_led == -3, f"ledger delta should be -3 relative to seed, got {delta_led}"

    # 三账口径：qty 的变化必须等于 ledger 的净变化
    assert qty0 + delta_led == qty_now, f"qty0({qty0}) + delta_led({delta_led}) != qty_now({qty_now})"
