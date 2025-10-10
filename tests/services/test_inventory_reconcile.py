# tests/services/test_inventory_reconcile.py
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.batch import Batch


@pytest.mark.asyncio
async def test_inventory_reconcile_up_and_down(session):
    from app.services.stock_service import StockService

    svc = StockService()

    item_id = 777
    loc = 1
    today = date.today()

    # 先造货：两个批次（一个过期，一个未来）
    for code, exp, qty in [
        ("CC-EXPIRED", today - timedelta(days=1), 5),
        ("CC-NEAR", today + timedelta(days=2), 7),
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=loc,
            delta=qty,
            reason="INBOUND",
            ref="CC-IN",
            batch_code=code,
            production_date=None,
            expiry_date=exp,
            mode="NORMAL",
        )

    # 当前应为 12；我们说实盘=15 → 盘盈 +3（入到 CC-ADJ-YYYYMMDD）
    res_up = await svc.reconcile_inventory(
        session=session, item_id=item_id, location_id=loc, counted_qty=15, apply=True
    )
    assert res_up["diff"] == 3
    assert abs(res_up["after_qty"] - 15) < 1e-9

    # 再说实盘=8 → 盘亏 -7（应先吃掉过期5，再吃近到期2）
    res_down = await svc.reconcile_inventory(
        session=session, item_id=item_id, location_id=loc, counted_qty=8, apply=True
    )
    assert res_down["diff"] == -7
    # 校验分批扣减：-5（过期） + -2（近到期）
    moves = dict(res_down["moves"])
    # 找到批次 id → code 映射
    id_code = {
        bid: bcode
        for bid, bcode in (await session.execute(select(Batch.id, Batch.batch_code))).all()
    }
    used_by_code = {id_code[k]: v for k, v in moves.items()}
    assert used_by_code["CC-EXPIRED"] == -5
    assert used_by_code["CC-NEAR"] in (-2, -2.0)

    # 最终库存应为 8
    assert abs(res_down["after_qty"] - 8) < 1e-9
