import pytest

pytestmark = pytest.mark.grp_core

from datetime import date, timedelta

from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def seed_batches(session, item, loc):
    from app.services.stock_service import StockService

    svc = StockService()
    today = date.today()
    # 过期更早的放前
    for code, days, qty in [("E1", 3, 4), ("E2", 10, 5), ("E3", None, 6)]:
        await svc.adjust(
            session=session,
            item_id=item,
            location_id=loc,
            delta=qty,
            reason="INBOUND",
            ref=f"FRV-{code}",
            batch_code=code,
            production_date=today,
            expiry_date=(today + timedelta(days=days)) if days is not None else None,
        )


async def test_fefo_rank_matches_outbound_choice(session):
    from app.services.outbound_service import OutboundService

    item, loc = 84001, 1
    await seed_batches(session, item, loc)
    await session.commit()

    # 视图：rank=1 应是最早到期批次
    rows = await session.execute(
        text(
            "SELECT batch_code FROM v_fefo_rank "
            "WHERE item_id=:i AND location_id=:l "
            "ORDER BY fefo_rank LIMIT 1"
        ),
        {"i": item, "l": loc},
    )
    top = rows.scalar()
    assert top == "E1"

    # 出库 3，应优先消耗 E1
    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref="FRV-SO",
        warehouse_id=1,
        lines=[{"line_no": "1", "item_id": item, "location_id": loc, "qty": 3}],
    )
    await session.commit()

    # 查看剩余批次 qty：E1 应被优先扣
    left = await session.execute(
        text(
            "SELECT batch_code, qty FROM batches "
            "WHERE item_id=:i AND location_id=:l "
            "ORDER BY batch_code"
        ),
        {"i": item, "l": loc},
    )
    remain = {r[0]: int(r[1] or 0) for r in left}
    assert remain["E1"] == 1  # 4-3=1
