# tests/services/test_snapshot_reconcile_v3.py
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService
from app.services.snapshot_service import SnapshotService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio

WAREHOUSE_ID = 1
ITEM_ID = 3003
BATCH_CODE = "NEAR"
ORDER_NO = "P3-SNAP-001"


async def _sum_ledger(session: AsyncSession) -> int:
    v = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
            FROM stock_ledger
            WHERE item_id=:i AND warehouse_id=:w AND batch_code=:b
        """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
    )
    return int(v.scalar() or 0)


async def _read_stocks(session: AsyncSession) -> int:
    row = await session.execute(
        text(
            """
            SELECT qty FROM stocks
            WHERE item_id=:i AND warehouse_id=:w AND batch_code=:b
            LIMIT 1
        """
        ),
        {"i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
    )
    r = row.first()
    return int(r[0]) if r else 0


async def _read_snapshot(session: AsyncSession, d: date) -> int:
    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(qty_on_hand),0)
            FROM stock_snapshots
            WHERE snapshot_date=:d AND item_id=:i AND warehouse_id=:w AND batch_code=:b
        """
        ),
        {"d": d, "i": ITEM_ID, "w": WAREHOUSE_ID, "b": BATCH_CODE},
    )
    r = row.first()
    return int(r[0] or 0)


async def test_snapshot_reconcile_same_day(session: AsyncSession):
    svc = StockService()

    # 0) 记录基线存量（由 conftest 预置：应为 10）
    qty_base = await _read_stocks(session)

    # 1) 入库 +20（增量）
    await svc.adjust(
        session=session,
        reason="INBOUND_RECEIVE",
        item_id=ITEM_ID,
        warehouse_id=WAREHOUSE_ID,
        batch_code=BATCH_CODE,
        delta=20,
        ref="SNAP:SEED",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
        expiry_date=date.today() + timedelta(days=180),
    )

    # 2) 出库 -3（增量）
    osvc = OutboundService()
    await osvc.commit(
        session=session,
        order_id=ORDER_NO,
        lines=[
            {"item_id": ITEM_ID, "warehouse_id": WAREHOUSE_ID, "batch_code": BATCH_CODE, "qty": 3}
        ],
        occurred_at=datetime.now(timezone.utc),
        warehouse_code="WH-1",
    )

    # 3) 生成当日快照（存量）
    await SnapshotService.run(session)
    snap_d = datetime.now(timezone.utc).date()

    # 4) 校验：stocks_base + Δledger == stocks_now == snapshot_T
    led = await _sum_ledger(session)  # Δ(+)20 + (-)3 = 17
    stk = await _read_stocks(session)  # 10 + 17 = 27
    snap = await _read_snapshot(session, snap_d)  # 27
    assert (
        qty_base + led == stk == snap
    ), f"base({qty_base}) + Δ({led}) != stocks({stk}) or snapshot({snap})"
