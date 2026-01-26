from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_events import handle_event_batch


async def _pick_one_stock_slot(session: AsyncSession):
    """
    从 stocks 中挑一个 (item_id, warehouse_id, batch_code, sum_qty)。
    若没有可用，则跳过测试。
    """
    row = await session.execute(
        text(
            """
            SELECT item_id, warehouse_id, batch_code, SUM(qty) AS qty
            FROM stocks
            WHERE qty > 0 AND batch_code IS NOT NULL
            GROUP BY item_id, warehouse_id, batch_code
            ORDER BY item_id, warehouse_id, batch_code
            LIMIT 1
            """
        )
    )
    r = row.first()
    if not r:
        pytest.skip("当前基线中没有带 batch_code 的 stocks 记录")
    return int(r[0]), int(r[1]), str(r[2]), int(r[3])


@pytest.mark.asyncio
async def test_platform_ship_consumes_soft_reserve_when_exists(session: AsyncSession):
    """
    场景：
      - 已存在一张 open reservation（platform=PDD, shop=SHOP1, wh=warehouse_id, ref=REF）
      - 平台发送 SHIP 事件（带 item_id/warehouse_id/batch_code/qty）

    新世界观下的预期（和当前实现对齐）：
      - reservation.status -> 'consumed'
      - reservation_lines.consumed_qty == qty
      - stock_ledger 中：
          * reason='OUTBOUND_SHIP' 对该 ref 的 delta == 0
          * reason='SOFT_SHIP'    对该 ref 的 delta == 0

    解释：
      - 这一条“有预占情况下的 SHIP”只负责消耗 reservation，
        不直接动库存；库存扣减由 Golden Flow 出库链路负责。
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 3:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试")

    platform = "pdd"
    shop_id = "SHOP1"
    ref = "PL-SHIP-RSV-1"
    qty = 3

    # 1) 先插入一张 reservation（open）
    #    ✅ 关键：warehouse_id 必须与 event 中一致，否则消费逻辑无法命中
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                'PDD', :shop_id, :warehouse_id, :ref,
                'open', now(), now(), now() + interval '30 minutes'
            )
            RETURNING id
            """
        ),
        {"shop_id": shop_id, "ref": ref, "warehouse_id": warehouse_id},
    )
    rid = res.scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line,
                item_id, qty, consumed_qty,
                created_at, updated_at
            )
            VALUES (
                :rid, 1,
                :item_id, :qty, 0,
                now(), now()
            )
            """
        ),
        {"rid": rid, "item_id": item_id, "qty": qty},
    )
    await session.commit()

    # 2) 构造平台 SHIP event
    raw_event = {
        "platform": platform,
        "order_sn": ref,
        "status": "SHIPPED",
        "shop_id": shop_id,
        "lines": [
            {
                "item_id": item_id,
                "warehouse_id": warehouse_id,
                "batch_code": batch_code,
                "qty": qty,
            }
        ],
    }

    await handle_event_batch([raw_event], session=session)

    # 3) reservation 应被消费
    row = await session.execute(
        text("SELECT status FROM reservations WHERE id = :rid"),
        {"rid": rid},
    )
    status = row.scalar_one()
    assert status == "consumed"

    row = await session.execute(
        text(
            """
            SELECT qty, consumed_qty
              FROM reservation_lines
             WHERE reservation_id = :rid AND ref_line = 1
            """
        ),
        {"rid": rid},
    )
    q, cq = row.fetchone()
    assert int(q) == qty
    assert int(cq) == qty

    # 4) ledger：这一条 SHIP 不动库存，两个 reason 都应为 0
    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = 'OUTBOUND_SHIP'
               AND item_id = :item_id
               AND warehouse_id = :warehouse_id
            """
        ),
        {
            "ref": ref,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
        },
    )
    out_delta = int(row.scalar() or 0)
    assert out_delta == 0

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = 'SOFT_SHIP'
               AND item_id = :item_id
               AND warehouse_id = :warehouse_id
            """
        ),
        {
            "ref": ref,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
        },
    )
    soft_delta = int(row.scalar() or 0)
    assert soft_delta == 0


@pytest.mark.asyncio
async def test_platform_ship_falls_back_to_outbound_when_no_reserve(session: AsyncSession):
    """
    场景：
      - 无任何 reservation（或 ref 不匹配）
      - 平台 SHIP 事件照常发来

    预期：
      - 不产生 reservations 记录
      - ledger 中 reason='OUTBOUND_SHIP' 有负数 delta
      - ledger 中 reason='SOFT_SHIP' 对同一 ref 为 0
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 2:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试")

    platform = "pdd"
    shop_id = "SHOP1"
    ref = "PL-SHIP-OUT-1"
    qty = 2

    # 确保当前没有这个 ref 的 reservation
    await session.execute(
        text(
            """
            DELETE FROM reservations
             WHERE platform = 'PDD'
               AND shop_id = :shop_id
               AND ref = :ref
            """
        ),
        {"shop_id": shop_id, "ref": ref},
    )
    await session.commit()

    raw_event = {
        "platform": platform,
        "order_sn": ref,
        "status": "SHIPPED",
        "shop_id": shop_id,
        "lines": [
            {
                "item_id": item_id,
                "warehouse_id": warehouse_id,
                "batch_code": batch_code,
                "qty": qty,
            }
        ],
    }

    await handle_event_batch([raw_event], session=session)

    # 1) 不应产生 reservation
    row = await session.execute(
        text(
            """
            SELECT COUNT(*)
              FROM reservations
             WHERE platform = 'PDD'
               AND shop_id = :shop_id
               AND ref = :ref
            """
        ),
        {"shop_id": shop_id, "ref": ref},
    )
    cnt_rsv = row.scalar_one()
    assert cnt_rsv == 0

    # 2) ledger 中应有 OUTBOUND_SHIP，且总和为 -qty
    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = 'OUTBOUND_SHIP'
               AND item_id = :item_id
               AND warehouse_id = :warehouse_id
            """
        ),
        {
            "ref": ref,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
        },
    )
    out_delta = int(row.scalar() or 0)
    assert out_delta == -qty

    # 3) 同一 ref 下 SOFT_SHIP 应为 0
    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = 'SOFT_SHIP'
               AND item_id = :item_id
               AND warehouse_id = :warehouse_id
            """
        ),
        {
            "ref": ref,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
        },
    )
    soft_delta = int(row.scalar() or 0)
    assert soft_delta == 0
