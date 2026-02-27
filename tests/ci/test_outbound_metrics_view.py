from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_metrics_view_basic(session: AsyncSession) -> None:
    # 视图存在
    reg = await session.execute(text("SELECT to_regclass('vw_outbound_metrics')"))
    assert reg.scalar() is not None, "vw_outbound_metrics view must exist"

    platform = "PDD"
    shop_id = "METRICS-SHOP"
    ref = f"ORD:{platform}:{shop_id}:UT-METRICS-001"

    # 选择 baseline 已存在的 item，避免引入额外 items/stocks_lot 依赖
    # base_seed.sql 已包含 item_id=1，且 stocks_lot 也有 (item_id=1, warehouse_id=1, lot_id=NULL) 槽位
    item_id = 1
    wh_id = 1

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

        # 4) 写一笔 PICK 落账：
        #    - batch_code 允许为 NULL（lot_id_key=0 语义），避免对账脚本在 lot-world 上产生歧义
        #    - after_qty 随便给个合理值，metrics 视图不依赖它
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger(
                    reason, ref, ref_line,
                    warehouse_id, item_id, batch_code,
                    delta, occurred_at, after_qty
                )
                VALUES (
                    'PICK', :r, 1,
                    :w, :i, NULL,
                    -3, now(), -3
                )
                """
            ),
            {"r": ref, "w": wh_id, "i": item_id},
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
        # ✅ 关键：清理本测试写入的持久数据，避免污染 make test 的 opening-ledger 对账关卡
        await session.execute(text("DELETE FROM audit_events WHERE category='OUTBOUND' AND ref=:r"), {"r": ref})
        await session.execute(text("DELETE FROM stock_ledger WHERE ref=:r"), {"r": ref})
        await session.commit()
