# tests/ci/test_db_invariants.py

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock.lots import ensure_lot_full
from app.services.stock_adjust import adjust_lot_impl
from tests.utils.ensure_minimal import ensure_item

pytestmark = pytest.mark.grp_snapshot  # 分组标记，可按需调整


async def _seed_wh_item_lot_stock(
    session: AsyncSession,
    *,
    wh_id: int,
    item_id: int,
    lot_code: str = "LEDGER-TEST-LOT",
) -> int:
    """
    Phase M-5 最小种子数据（lot-world，终态写入入口）：

    - warehouses：确保存在
    - items：确保存在（Phase M policy NOT NULL）
    - lots：ensure_lot_full（唯一入口，禁止 tests 直接 INSERT INTO lots）
    - ledger+stocks_lot：adjust_lot_impl（唯一写入器，禁止 tests 直接 INSERT/UPDATE stocks_lot/stock_ledger）

    返回 lot_id。
    """
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:wh_id, 'WH-LEDGER-TEST')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"wh_id": int(wh_id)},
    )

    await ensure_item(session, id=int(item_id), sku=f"SKU-{int(item_id)}", name=f"Item-{int(item_id)}")

    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_code=str(lot_code),
        production_date=None,
        expiry_date=None,
    )

    # 用唯一写入器写一条 COUNT（delta=1 -> after=1），同时确保 stocks_lot 槽位存在且与 ledger 一致
    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_id=int(lot_id),
        delta=1,
        reason="COUNT",
        ref="TRG-TEST",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
        meta=None,
        batch_code=str(lot_code),
        production_date=None,
        expiry_date=None,
        trace_id=None,
        utc_now=lambda: datetime.now(timezone.utc),
        shadow_write_stocks=False,
    )

    await session.commit()
    return int(lot_id)


@pytest.mark.asyncio
async def test_ledger_row_consistent_with_stock_slot(session: AsyncSession):
    """
    lot-world 行为验证（终态口径）：

    - 通过 adjust_lot_impl 写入一条 COUNT（显式 lot_id）
    - 再 JOIN stocks_lot/lots 校验 ledger 的维度与 lot-world 槽位一致（展示码来自 lots.lot_code）
    """
    wh_id, item_id = 1, 99901
    lot_code = "LEDGER-TEST-LOT"

    lot_id = await _seed_wh_item_lot_stock(session, wh_id=wh_id, item_id=item_id, lot_code=lot_code)

    # 通过 ref/ref_line 定位刚刚写入的 ledger 行（避免直接 INSERT stock_ledger）
    row = await session.execute(
        text(
            """
            SELECT id
              FROM stock_ledger
             WHERE warehouse_id = :wh_id
               AND item_id = :item_id
               AND lot_id = :lot_id
               AND ref = 'TRG-TEST'
               AND ref_line = 1
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"wh_id": int(wh_id), "item_id": int(item_id), "lot_id": int(lot_id)},
    )
    ledger_id = row.scalar_one_or_none()
    assert ledger_id is not None, "ledger row not found"

    row2 = await session.execute(
        text(
            """
            SELECT
              l.warehouse_id AS l_wh,
              l.item_id      AS l_item,
              l.lot_id       AS l_lot,
              lo_l.lot_code  AS l_code,
              sl.warehouse_id AS s_wh,
              sl.item_id      AS s_item,
              sl.lot_id       AS s_lot,
              lo_s.lot_code   AS s_code
            FROM stock_ledger AS l
            LEFT JOIN lots lo_l ON lo_l.id = l.lot_id
            JOIN stocks_lot AS sl
              ON sl.warehouse_id = l.warehouse_id
             AND sl.item_id      = l.item_id
             AND sl.lot_id       = l.lot_id
            LEFT JOIN lots lo_s ON lo_s.id = sl.lot_id
           WHERE l.id = :lid
            """
        ),
        {"lid": int(ledger_id)},
    )
    r = row2.mappings().first()
    assert r is not None, "ledger row not found via join to stocks_lot"

    assert int(r["l_wh"]) == int(r["s_wh"]) == int(wh_id)
    assert int(r["l_item"]) == int(r["s_item"]) == int(item_id)
    assert int(r["l_lot"]) == int(r["s_lot"]) == int(lot_id)
    assert str(r["l_code"]) == str(r["s_code"]) == str(lot_code)
