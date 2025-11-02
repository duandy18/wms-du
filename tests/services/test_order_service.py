from datetime import date, timedelta

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed(session, item_id=1, wh=1, loc=1):
    """
    造数：为 item=1 准备两个批次并落地 onhand（直接写入 stocks 的必填列）
      - B1（临期优先）3 件
      - B2（远期）     5 件

    说明：
    - 你的 stocks 表对 item_id / warehouse_id / location_id / batch_id / batch_code / qty
      都有口径要求（其中 batch_code 为 NOT NULL），故以六列完整插入。
    """
    today = date.today()
    plan = [
        ("B1", today + timedelta(days=2), 3),
        ("B2", today + timedelta(days=10), 5),
    ]

    # 1) 插入批次并取回 batch_id
    batch_ids = {}
    for code, exp, qty in plan:
        bid = (
            await session.execute(
                text(
                    """
                    INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, expire_at)
                    VALUES (:item, :wh, :loc, :code, :exp)
                    RETURNING id
                """
                ),
                {"item": item_id, "wh": wh, "loc": loc, "code": code, "exp": exp},
            )
        ).scalar_one()
        batch_ids[code] = int(bid)

    # 2) 以六列完整写入 onhand（避免 NOT NULL 违反）
    for code, _, qty in plan:
        await session.execute(
            text(
                """
                INSERT INTO stocks(item_id, warehouse_id, location_id, batch_id, batch_code, qty)
                VALUES (:item, :wh, :loc, :bid, :code, :qty)
            """
            ),
            {
                "item": item_id,
                "wh": wh,
                "loc": loc,
                "bid": batch_ids[code],
                "code": code,
                "qty": int(qty),
            },
        )

    await session.commit()
    return {"b1": batch_ids["B1"], "b2": batch_ids["B2"]}


async def _reservations_by_batch(session, order_id: int):
    rows = (
        await session.execute(
            text(
                """
                SELECT batch_id, SUM(qty) AS q
                FROM reservations
                WHERE order_id = :oid
                GROUP BY batch_id
                ORDER BY batch_id
            """
            ),
            {"oid": order_id},
        )
    ).all()
    return {int(bid): int(q) for bid, q in rows}


async def _sum_onhand(session, item_id: int) -> int:
    """
    onhand = SUM(stocks.qty) WHERE item_id=...
    """
    return int(
        (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(qty),0)
                    FROM stocks
                    WHERE item_id = :item
                """
                ),
                {"item": item_id},
            )
        ).scalar()
        or 0
    )


async def _sum_available(session, item_id: int) -> int:
    """
    可用量口径：available = onhand(stocks) - reserved(reservations)
    其中 reserved 通过 reservations JOIN batches 过滤到同一 item。
    """
    return int(
        (
            await session.execute(
                text(
                    """
                    WITH onhand AS (
                      SELECT COALESCE(SUM(s.qty),0) AS q
                      FROM stocks s
                      WHERE s.item_id=:item
                    ),
                    reserved AS (
                      SELECT COALESCE(SUM(r.qty),0) AS q
                      FROM reservations r
                      JOIN batches b ON b.id = r.batch_id
                      WHERE b.item_id=:item
                    )
                    SELECT (SELECT q FROM onhand) - (SELECT q FROM reserved)
                """
                ),
                {"item": item_id},
            )
        ).scalar()
        or 0
    )


async def test_fefo_reserve_then_cancel(session):
    """
    目标：按 order_id 执行 FEFO 预留与取消。
    预期：
      1) 预留时分摊到 B1(3) + B2(1)，合计 4；
      2) 预留只影响 reservations，可用量下降 4，onhand 不变；
      3) 取消后 reservations 清空，可用量恢复。
    """
    from app.services.order_service import OrderService

    # 造数：B1=3、B2=5 → 总 onhand=8
    ids = await _seed(session)
    b1_id, b2_id = ids["b1"], ids["b2"]

    before_onhand = await _sum_onhand(session, item_id=1)
    before_available = await _sum_available(session, item_id=1)
    assert before_onhand == 8
    assert before_available == 8

    svc = OrderService()

    # 1) 创建订单（单行需求 4）
    oid = await svc.create_order(
        session=session, item_id=1, warehouse_id=1, qty=4, client_ref="REF-1"
    )

    # 2) 预留：应按 FEFO 分配为 B1:3、B2:1（只写 reservations）
    res = await svc.reserve(session=session, order_id=oid)
    assert res["order_id"] == oid

    alloc = await _reservations_by_batch(session, oid)
    assert alloc.get(b1_id, 0) == 3
    assert alloc.get(b2_id, 0) == 1
    assert sum(alloc.values()) == 4

    # 可用量下降 4；onhand 不变
    after_available = await _sum_available(session, item_id=1)
    assert after_available == before_available - 4
    assert await _sum_onhand(session, item_id=1) == before_onhand

    # 3) 取消：清空该单 reservations；可用量回到初值；onhand 仍不变
    await svc.cancel(session=session, order_id=oid)
    alloc2 = await _reservations_by_batch(session, oid)
    assert sum(alloc2.values()) == 0

    after_cancel_available = await _sum_available(session, item_id=1)
    assert after_cancel_available == before_available
    assert await _sum_onhand(session, item_id=1) == before_onhand
