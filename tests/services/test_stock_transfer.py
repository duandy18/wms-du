# tests/services/test_stock_transfer.py
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.batch import Batch


@pytest.mark.asyncio
async def test_stock_transfer_fefo(session):
    from app.services.stock_service import StockService

    svc = StockService()

    item_id = 606
    src = 1
    dst = 2
    today = date.today()

    # 源库位造三批：过期5、近到期7、远期9
    for code, exp, qty in [
        ("T-EXP", today - timedelta(days=1), 5),
        ("T-NEAR", today + timedelta(days=3), 7),
        ("T-FAR", today + timedelta(days=90), 9),
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=src,
            delta=qty,
            reason="INBOUND",
            ref="T-IN",
            batch_code=code,
            production_date=None,
            expiry_date=exp,
            mode="NORMAL",
        )

    # 调拨 10：默认不允许过期 → 应扣 NEAR=7 + FAR=3
    res = await svc.transfer(
        session=session,
        item_id=item_id,
        src_location_id=src,
        dst_location_id=dst,
        qty=10,
        allow_expired=False,
        reason="TRANSFER",
        ref="T-MOVE",
    )
    assert res["total_moved"] == 10

    # 校验 moves：应无 T-EXP；应含 T-NEAR 7 与 T-FAR 3
    id_code = {
        bid: bcode
        for bid, bcode in (await session.execute(select(Batch.id, Batch.batch_code))).all()
    }
    code_by_dst = {id_code[m["dst_batch_id"]]: m["qty"] for m in res["moves"]}
    assert "T-EXP" not in code_by_dst
    assert code_by_dst["T-NEAR"] == 7
    assert code_by_dst["T-FAR"] == 3

    # --- 关键修复：把辅助函数改为 async，并在调用处 await ---
    async def q_qty(code: str, loc: int) -> int:
        return (
            await session.execute(
                select(Batch.qty).where(Batch.batch_code == code, Batch.location_id == loc)
            )
        ).scalar_one()

    # 源批次数量变化：EXP=5 尚在；NEAR=0；FAR=6
    assert await q_qty("T-EXP", src) == 5
    assert await q_qty("T-NEAR", src) == 0
    assert await q_qty("T-FAR", src) == 6

    # 目标批次增长：NEAR=7、FAR=3，对应批次码保持一致
    assert await q_qty("T-NEAR", dst) == 7
    assert await q_qty("T-FAR", dst) == 3
