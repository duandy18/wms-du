# tests/services/test_stock_fefo.py
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.batch import Batch


@pytest.mark.asyncio
async def test_stock_fefo_outbound(session):
    from app.services.stock_service import StockService

    svc = StockService()

    item_id = 202
    location_id = 1
    today = date.today()

    for code, exp, qty in [
        ("X-EXP", today - timedelta(days=2), 5),  # 已过期
        ("X-NEAR", today + timedelta(days=1), 7),  # 近到期
        ("X-FAR", today + timedelta(days=90), 9),  # 远期
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=qty,
            reason="INBOUND",
            ref="TEST-IN",
            batch_code=code,
            production_date=today - timedelta(days=10),
            expiry_date=exp,
            mode="NORMAL",
        )

    # 明确允许消耗过期：应先扣已过期，再扣近到期
    res = await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-10,
        reason="OUTBOUND",
        ref="TEST-OUT",
        mode="FEFO",
        allow_expired=True,  # ← 允许过期
    )
    code_by_id = {
        bid: bcode
        for (bid, bcode) in (await session.execute(select(Batch.id, Batch.batch_code))).all()
    }
    used_by_code = {code_by_id[bid]: used for (bid, used) in res["batch_moves"]}
    assert used_by_code["X-EXP"] == -5
    assert used_by_code["X-NEAR"] == -5
    assert "X-FAR" not in used_by_code

    # 第二次：剩余 11（NEAR=2, FAR=9）
    res2 = await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-11,
        reason="OUTBOUND",
        ref="TEST-OUT2",
        mode="FEFO",
        allow_expired=True,  # ← 允许过期
    )
    used2_by_code = {code_by_id[bid]: used for (bid, used) in res2["batch_moves"]}
    assert used2_by_code["X-NEAR"] == -2
    assert used2_by_code["X-FAR"] == -9


@pytest.mark.asyncio
async def test_stock_fefo_disallow_expired_by_default(session):
    """默认不传 allow_expired → False，应不消费已过期批次。"""
    from app.services.stock_service import StockService

    svc = StockService()

    item_id = 303
    location_id = 1
    today = date.today()

    for code, exp, qty in [
        ("E-EXP", today - timedelta(days=1), 5),  # 已过期
        ("E-NEAR", today + timedelta(days=2), 7),  # 近到期
        ("E-FAR", today + timedelta(days=60), 9),  # 远期
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=qty,
            reason="INBOUND",
            ref="TEST-IN-2",
            batch_code=code,
            production_date=today - timedelta(days=10),
            expiry_date=exp,
            mode="NORMAL",
        )

    # 不传 allow_expired（默认 False）：应跳过已过期，扣 NEAR 7 + FAR 3
    res = await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-10,
        reason="OUTBOUND",
        ref="TEST-OUT-2",
        mode="FEFO",
        # 不传 allow_expired
    )
    code_by_id = {
        bid: bcode
        for (bid, bcode) in (await session.execute(select(Batch.id, Batch.batch_code))).all()
    }
    used_by_code = {code_by_id[bid]: used for (bid, used) in res["batch_moves"]}

    assert "E-EXP" not in used_by_code  # 不应动已过期批次
    assert used_by_code["E-NEAR"] == -7
    assert used_by_code["E-FAR"] == -3
