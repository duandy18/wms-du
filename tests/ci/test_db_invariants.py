# tests/ci/test_db_invariants.py

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    Phase M-5 最小种子数据（lot-world）：

    - warehouses：确保存在
    - items：确保存在（Phase M policy NOT NULL）
    - lots：确保存在 SUPPLIER lot（lot_code 非空，且冻结 policy snapshots）
    - stocks_lot：插入对应槽位（qty=0）

    返回 lot_id。

    说明（重要）：
    - 以真实 DB 结构为准：不假设 lots 上存在某个 ON CONFLICT 的唯一约束组合；
      因此这里采用“先查再插”避免对约束名/列组合的猜测。
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

    # 1) try select existing SUPPLIER lot by natural key (wh,item,code)
    row0 = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 1
                """
            ),
            {"w": int(wh_id), "i": int(item_id), "code": str(lot_code)},
        )
    ).first()
    if row0 is not None:
        lot_id = int(row0[0])
    else:
        # 2) insert (no ON CONFLICT guessing)
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    source_receipt_id,
                    source_line_no,
                    -- required policy snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional shelf-life snapshots (nullable)
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.shelf_life_value,
                    it.shelf_life_unit
                  FROM items it
                 WHERE it.id = :i
                """
            ),
            {"w": int(wh_id), "i": int(item_id), "code": str(lot_code)},
        )
        # 3) re-select
        row1 = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id = :i
                       AND lot_code_source = 'SUPPLIER'
                       AND lot_code = :code
                     LIMIT 1
                    """
                ),
                {"w": int(wh_id), "i": int(item_id), "code": str(lot_code)},
            )
        ).first()
        assert row1 is not None, "failed to ensure lot"
        lot_id = int(row1[0])

    await session.execute(
        text(
            """
            INSERT INTO stocks_lot (warehouse_id, item_id, lot_id, qty)
            VALUES (:w, :i, :lot, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"w": int(wh_id), "i": int(item_id), "lot": int(lot_id)},
    )

    await session.commit()
    return int(lot_id)


@pytest.mark.asyncio
async def test_ledger_row_consistent_with_stock_slot(session: AsyncSession):
    """
    lot-world 行为验证：

    - 先造一个 stocks_lot 槽位 (warehouse_id, item_id, lot_id, qty)
    - 再往 stock_ledger 写一条 COUNT 记录（显式写 lot_id）
    - 通过 JOIN stocks_lot/lots 校验 ledger 的维度与 lot-world 槽位一致（展示码来自 lots.lot_code）
    """
    wh_id, item_id = 1, 99901
    lot_code = "LEDGER-TEST-LOT"

    lot_id = await _seed_wh_item_lot_stock(session, wh_id=wh_id, item_id=item_id, lot_code=lot_code)

    now = datetime.now(timezone.utc)
    row = await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
                warehouse_id,
                item_id,
                lot_id,
                reason,
                ref,
                ref_line,
                delta,
                occurred_at,
                after_qty
            )
            VALUES (
                :wh_id,
                :item_id,
                :lot_id,
                'COUNT',
                'TRG-TEST',
                1,
                1,
                :ts,
                1
            )
            RETURNING id
            """
        ),
        {
            "wh_id": int(wh_id),
            "item_id": int(item_id),
            "lot_id": int(lot_id),
            "ts": now,
        },
    )
    ledger_id = int(row.scalar_one())

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
