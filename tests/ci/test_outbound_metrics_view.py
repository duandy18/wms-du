from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock.lots import ensure_internal_lot_singleton
from app.services.stock_adjust import adjust_lot_impl

pytestmark = pytest.mark.asyncio

UTC = timezone.utc


async def _pick_one_lot_id_for_item(session: AsyncSession, *, warehouse_id: int, item_id: int) -> int:
    """
    终态：stock_ledger 必须带 lot_id（lot-world）。
    从 stocks_lot 中挑一个现存槽位的 lot_id（qty 可以为 0）。

    Phase M-5 收口后 baseline 不再隐式种 stocks_lot 槽位，因此：
    - 若不存在槽位：显式 seed 一个 INTERNAL lot 槽位（delta=+1），再返回 lot_id。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT lot_id
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = :i
                 ORDER BY id
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    if row is not None:
        return int(row[0])

    # 显式 seed：创建 INTERNAL singleton lot + 写入一笔 delta=+1（确保 stocks_lot slot 被 materialize）
    lot_id = await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        source_receipt_id=None,
        source_line_no=None,
    )

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=1,
        reason="UT_METRICS_SEED",
        ref="ut:metrics:seed",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        meta=None,
        batch_code=None,
        production_date=None,
        expiry_date=None,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
        shadow_write_stocks=False,
    )

    row2 = (
        await session.execute(
            text(
                """
                SELECT lot_id
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = :i
                 ORDER BY id
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    assert row2 is not None, {"msg": "failed to seed stocks_lot slot for item", "warehouse_id": warehouse_id, "item_id": item_id}
    return int(row2[0])


@pytest.mark.asyncio
async def test_metrics_view_basic(session: AsyncSession) -> None:
    # 视图存在
    reg = await session.execute(text("SELECT to_regclass('vw_outbound_metrics')"))
    assert reg.scalar() is not None, "vw_outbound_metrics view must exist"

    platform = "PDD"
    shop_id = "METRICS-SHOP"
    ref = f"ORD:{platform}:{shop_id}:UT-METRICS-001"

    # 选择 baseline 已存在的 item，避免引入额外 items/stocks_lot 依赖
    item_id = 1
    wh_id = 1

    # 终态：需要一个真实 lot_id（若 baseline 无 slot，则显式 seed）
    lot_id = await _pick_one_lot_id_for_item(session, warehouse_id=wh_id, item_id=item_id)

    # 2) 清理同 ref 残留（先清再写，保证幂等复跑）
    await session.execute(text("DELETE FROM audit_events WHERE category='OUTBOUND' AND ref=:r"), {"r": ref})
    await session.execute(text("DELETE FROM stock_ledger WHERE ref=:r"), {"r": ref})
    await session.commit()

    try:
        # 3) 写 ORDER_CREATED + SHIP_COMMIT 审计事件（平台口径：platform='PDD'）
        await session.execute(
            text(
                """INSERT INTO audit_events(category, ref, meta, created_at)
                    VALUES ('OUTBOUND', :r, '{"flow":"OUTBOUND","event":"ORDER_CREATED","platform":"PDD"}'::jsonb, now())"""
            ),
            {"r": ref},
        )
        await session.execute(
            text(
                """INSERT INTO audit_events(category, ref, meta, created_at)
                    VALUES ('OUTBOUND', :r, '{"flow":"OUTBOUND","event":"SHIP_COMMIT","platform":"PDD"}'::jsonb, now())"""
            ),
            {"r": ref},
        )

        # 4) 写一笔 PICK 落账（lot-world：必须带 lot_id）
        # ✅ 终态约束：after_qty >= 0，因此不得写负数。
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger(
                    reason, ref, ref_line,
                    warehouse_id, item_id, lot_id,
                    delta, occurred_at, after_qty
                )
                VALUES (
                    'PICK', :r, 1,
                    :w, :i, :lot,
                    -3, now(), 0
                )
                """
            ),
            {"r": ref, "w": wh_id, "i": item_id, "lot": int(lot_id)},
        )
        await session.commit()

        # 5) 查视图：今天、平台=PDD
        q = await session.execute(
            text(
                """
                SELECT day, warehouse_id, platform, orders_created, ship_commits, pick_qty
                FROM vw_outbound_metrics
                WHERE day = (now() at time zone 'utc')::date AND platform = :p
                ORDER BY warehouse_id
                """
            ),
            {"p": platform},
        )
        rows = q.fetchall()
        assert rows, "expect some rows in vw_outbound_metrics"

        total_orders = sum(r[3] for r in rows)
        total_ships = sum(r[4] for r in rows)
        total_picks = sum(r[5] for r in rows)

        assert total_orders >= 1, f"expected >=1 ORDER_CREATED, got {total_orders}"
        assert total_ships >= 1, f"expected >=1 SHIP_COMMIT, got {total_ships}"
        assert total_picks >= 3, f"expected PICK qty >=3, got {total_picks}"

        # 至少应有一行 warehouse_id=1 的数据（我们插入的那笔 PICK）
        assert any(r[1] == wh_id for r in rows)
        # 平台口径稳定
        assert all(r[2] == platform for r in rows)

    finally:
        # 若前面 SQL 失败导致事务中止，必须 rollback 才能继续清理
        await session.rollback()
        await session.execute(text("DELETE FROM audit_events WHERE category='OUTBOUND' AND ref=:r"), {"r": ref})
        await session.execute(text("DELETE FROM stock_ledger WHERE ref=:r"), {"r": ref})
        await session.commit()
