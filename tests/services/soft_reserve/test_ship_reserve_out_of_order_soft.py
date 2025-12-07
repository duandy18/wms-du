# tests/services/soft_reserve/test_ship_reserve_out_of_order_soft.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.soft_reserve_service import SoftReserveService

UTC = timezone.utc

pytestmark = pytest.mark.asyncio


async def _seed_batch_and_stock(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES (:item, :wh, :code, NULL)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": batch_code},
    )
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item, :wh, :code, :qty)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": batch_code, "qty": qty},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_soft_reserve_ship_then_reserve_out_of_order(session: AsyncSession):
    """
    v2 语义的乱序容错：SHIP 先到 / RESERVE 后到

    1) 第一次 pick_consume 在没有 reservation 的情况下返回 NOOP；
    2) 持久化 reservation (open)；
    3) 第二次 pick_consume 正常消费 reservation，使状态变为 consumed；
       不再要求 soft reserve 层直接写台账/扣库存。
    """
    svc = SoftReserveService()

    platform = "PDD"
    shop_id = "S1"
    warehouse_id = 1
    item_id = 3002
    batch_code = "B-OOO-1"
    ref = "SR-OUTOFORDER-1"

    # 造 3 件库存（仓 + 批次）
    await _seed_batch_and_stock(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        qty=3,
    )

    # Step 1: SHIP 先到 —— 无 reservation，应该 NOOP
    r1 = await svc.pick_consume(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        occurred_at=datetime.now(UTC),
    )
    assert r1["status"] == "NOOP"

    # 不应写任何负账
    row = await session.execute(
        text("SELECT COUNT(*) FROM stock_ledger WHERE ref=:ref AND delta<0"),
        {"ref": ref},
    )
    assert int(row.scalar() or 0) == 0

    # Step 2: RESERVE 后到 —— 持久化 open reservation
    await svc.persist(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        lines=[{"item_id": item_id, "qty": 3}],
    )

    # Step 3: 再次 SHIP —— 正常消费 reservation
    r2 = await svc.pick_consume(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        occurred_at=datetime.now(UTC),
    )
    assert r2["status"] in ("CONSUMED", "PARTIAL")

    # reservation 状态 consumed
    row = await session.execute(
        text(
            """
            SELECT status
              FROM reservations
             WHERE platform=:p AND shop_id=:s AND warehouse_id=:w AND ref=:r
            """
        ),
        {"p": platform, "s": shop_id, "w": warehouse_id, "r": ref},
    )
    status = row.scalar_one()
    assert status.lower() == "consumed"
