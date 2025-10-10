from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.batch import Batch
from app.models.location import Location


@pytest.mark.asyncio
async def test_auto_transfer_expired(session):
    from app.services.stock_service import StockService

    svc = StockService()

    today = date.today()
    warehouse_id = 1
    # 构造库位：1=默认，异常区名用 EXPIRED_ZONE（Service 会自动创建）
    src_loc = 1

    # 造三批：过期 5、近到期 7、远期 9（同一 item）
    item_id = 909
    for code, exp, qty in [
        ("E-EXP", today - timedelta(days=1), 5),
        ("E-NEAR", today + timedelta(days=2), 7),
        ("E-FAR", today + timedelta(days=60), 9),
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=src_loc,
            delta=qty,
            reason="INBOUND",
            ref="AUTO-IN",
            batch_code=code,
            production_date=today - timedelta(days=30),
            expiry_date=exp,
            mode="NORMAL",
        )

    # 执行自动转移（只应转移已过期批次 E-EXP=5）
    result = await svc.auto_transfer_expired(
        session=session,
        warehouse_id=warehouse_id,
        to_location_id=None,  # 让它自动建 EXPIRED_ZONE
        to_location_name="EXPIRED_ZONE",
        item_ids=None,
        dry_run=False,
    )
    assert result["moved_total"] == 5
    moves = result["moves"]
    assert len(moves) == 1 and moves[0]["batch_code"] == "E-EXP" and moves[0]["qty_moved"] == 5

    # 源批次应为 0，目标库位应有同批次 +5
    # 找目标库位 id
    dst_loc_id = (
        await session.execute(select(Location.id).where(Location.name == "EXPIRED_ZONE"))
    ).scalar_one()
    # 源/目标批次
    src_qty = (
        await session.execute(
            select(Batch.qty).where(Batch.batch_code == "E-EXP", Batch.location_id == src_loc)
        )
    ).scalar_one()
    dst_qty = (
        await session.execute(
            select(Batch.qty).where(Batch.batch_code == "E-EXP", Batch.location_id == dst_loc_id)
        )
    ).scalar_one()
    assert src_qty == 0
    assert dst_qty == 5
