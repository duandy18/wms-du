# tests/services/soft_reserve/test_ship_replay_concurrency_soft.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
    """
    仅按 (item, warehouse, batch_code) 造数，qty 为“覆盖值”而不是累加，
    避免与 _db_clean_and_seed 的基线叠加。
    """
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


async def _get_reservation_status(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    ref: str,
) -> str | None:
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
    return row.scalar_one_or_none()


@pytest.mark.asyncio
async def test_soft_reserve_pick_consume_idempotent_under_concurrency(
    async_session_maker: async_sessionmaker[AsyncSession],
):
    """
    v2 语义：并发 pick_consume 只会让一次消费生效，其余为 NOOP/重复调用。

    - reservations 状态最终收敛为 consumed；
    - 不要求 soft reserve 层直接写库存/台账（由 Outbound 负责）。
    """
    svc = SoftReserveService()

    platform = "PDD"
    shop_id = "S1"
    warehouse_id = 1
    item_id = 3001
    batch_code = "B-CONC-1"
    ref = "SR-CONC-1"

    # 1) 用一个短生命周期 Session 造数据：库存=3，reservation=open
    async with async_session_maker() as s0:
        await _seed_batch_and_stock(
            s0,
            item_id=item_id,
            warehouse_id=warehouse_id,
            batch_code=batch_code,
            qty=3,
        )
        await svc.persist(
            s0,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            ref=ref,
            lines=[{"item_id": item_id, "qty": 3}],
        )
        await s0.commit()

    # 2) 并发 10 次 pick_consume，每个 worker 独立 Session
    async def worker() -> dict:
        async with async_session_maker() as s:
            return await svc.pick_consume(
                s,
                platform=platform,
                shop_id=shop_id,
                warehouse_id=warehouse_id,
                ref=ref,
                occurred_at=datetime.now(UTC),
            )

    results = await asyncio.gather(*[worker() for _ in range(10)])

    statuses = {r["status"] for r in results}
    # 至少有一次真正消费，其余为 NOOP/重复调用
    assert statuses <= {"CONSUMED", "PARTIAL", "NOOP"}
    assert "CONSUMED" in statuses or "PARTIAL" in statuses

    # 3) 最终状态应为 consumed
    async with async_session_maker() as s1:
        final_status = await _get_reservation_status(
            s1,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            ref=ref,
        )
        assert final_status is not None
        assert final_status.lower() == "consumed"
