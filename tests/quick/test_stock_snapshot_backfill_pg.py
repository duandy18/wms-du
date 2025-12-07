from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.jobs.snapshot import run_once
from app.services.ledger_writer import write_ledger

pytestmark = pytest.mark.asyncio


async def _qty_col(session: AsyncSession) -> str:
    """检测 stock_snapshots 的数量列：优先 qty_on_hand，其次 qty。"""
    rows = await session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stock_snapshots'
            """
        )
    )
    names = {r[0] for r in rows.fetchall()}
    if "qty_on_hand" in names:
        return "qty_on_hand"
    if "qty" in names:
        return "qty"
    raise RuntimeError("stock_snapshots has neither 'qty_on_hand' nor 'qty' column")


async def _ins_item(session: AsyncSession, sku: str) -> int:
    await session.execute(
        text("INSERT INTO items (sku,name) VALUES (:s,:n) ON CONFLICT DO NOTHING"),
        {"s": sku, "n": sku},
    )
    row = await session.execute(
        text("SELECT id FROM items WHERE sku = :s"),
        {"s": sku},
    )
    return int(row.scalar_one())


async def _ensure_wh_and_batch(
    session: AsyncSession,
    *,
    wh_id: int,
    item_id: int,
    batch_code: str,
) -> None:
    # warehouse
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:w, 'WH-SNAP-BF')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"w": wh_id},
    )

    # batch
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES (:item_id, :w, :b, NULL)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item_id": item_id, "w": wh_id, "b": batch_code},
    )

    # stocks 槽位，初始 qty=0
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item_id, :w, :b, 0)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": item_id, "w": wh_id, "b": batch_code},
    )


async def test_backfill(
    session: AsyncSession,
    async_engine: AsyncEngine,
):
    """
    Backfill 行为验证（v2）：

    场景：
      - 同一 (wh,item,batch) 在 T-1 有一笔 +2 台账，在 T 有一笔 +5；
      - 先跑 cut = T 00:00；
      - 再回灌 cut = T-1 00:00；
      - 期望：
          * T-1 的 snapshot 记录数量为 2.0；
          * T 的 snapshot 仍为 5.0，不受回灌影响。
    """

    # 造维度
    item_id = await _ins_item(session, "SNAP-2")
    wh_id = 1
    batch_code = "SNAP-B2"

    await _ensure_wh_and_batch(
        session,
        wh_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
    )

    dayT = datetime(2025, 10, 10, tzinfo=UTC)
    dayT_1 = datetime(2025, 10, 9, tzinfo=UTC)

    # 写台账：T-1 +2，T +5
    await write_ledger(
        session,
        warehouse_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
        reason="TEST",
        delta=2,
        after_qty=2,  # 任意合法值，snapshot 逻辑主要关心 delta
        ref="R1",
        ref_line=1,
        occurred_at=dayT_1.replace(hour=10),
        trace_id=None,
    )
    await write_ledger(
        session,
        warehouse_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
        reason="TEST",
        delta=5,
        after_qty=7,  # 任意合法值
        ref="R2",
        ref_line=1,
        occurred_at=dayT.replace(hour=10),
        trace_id=None,
    )
    await session.commit()

    # 先跑 T（cut=T 00:00）
    await run_once(async_engine, grain="day", at=dayT, prev=None)

    # 再回灌 T-1（cut=T-1 00:00），不应污染 T 的结果
    await run_once(async_engine, grain="day", at=dayT_1, prev=None)

    qcol = await _qty_col(session)

    qT_1 = (
        await session.execute(
            text(
                f"""
                SELECT {qcol}
                  FROM stock_snapshots
                 WHERE snapshot_date = :c
                   AND item_id       = :i
                   AND warehouse_id  = :w
                   AND batch_code    = :b
                """
            ),
            {"c": dayT_1.date(), "i": item_id, "w": wh_id, "b": batch_code},
        )
    ).scalar_one()

    qT = (
        await session.execute(
            text(
                f"""
                SELECT {qcol}
                  FROM stock_snapshots
                 WHERE snapshot_date = :c
                   AND item_id       = :i
                   AND warehouse_id  = :w
                   AND batch_code    = :b
                """
            ),
            {"c": dayT.date(), "i": item_id, "w": wh_id, "b": batch_code},
        )
    ).scalar_one()

    assert float(qT_1) == 2.0
    assert float(qT) == 5.0
