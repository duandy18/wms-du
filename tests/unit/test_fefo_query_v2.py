# tests/unit/test_fefo_query_v2.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_fallbacks import FefoAllocator


@pytest.mark.asyncio
async def test_fefo_query_returns_sorted_not_enforcing(session: AsyncSession):
    """
    v2 FEFO 查询 smoke（lot-world）：

    - 同一仓库下，准备两个 lot：
      * A_NEAR：expiry = +1 day
      * B_FAR ：expiry = +10 days
    - stocks_lot 中各放 3 件；
    - 申请 need_qty=2；
    - 期望：
      * 计划列表中至少有一条；
      * 第一条来自 A_NEAR（最近到期优先）；
      * 第一条的 take_qty = 2（在最早批次中优先消耗）。
    """

    # 1) 准备 lots（SUPPLIER：必须 lot_code 非空，且 source_receipt_id/source_line_no 必须为 NULL）
    lot_rows = (
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    production_date,
                    expiry_date,
                    expiry_source
                ) VALUES
                  (1, 3003, 'SUPPLIER', 'A_NEAR', CURRENT_DATE, CURRENT_DATE + INTERVAL '1 day',  'EXPLICIT'),
                  (1, 3003, 'SUPPLIER', 'B_FAR',  CURRENT_DATE, CURRENT_DATE + INTERVAL '10 day', 'EXPLICIT')
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET
                    expiry_date = EXCLUDED.expiry_date
                RETURNING id, lot_code
                """
            )
        )
    ).all()

    # 兜底再查一次（兼容不同 PG 行为）
    if len(lot_rows) < 2:
        lot_rows = (
            await session.execute(
                text(
                    """
                    SELECT id, lot_code
                      FROM lots
                     WHERE warehouse_id = 1
                       AND item_id = 3003
                       AND lot_code_source = 'SUPPLIER'
                       AND lot_code IN ('A_NEAR', 'B_FAR')
                     ORDER BY lot_code ASC
                    """
                )
            )
        ).all()

    lot_id_by_code: dict[str, int] = {}
    for r in lot_rows:
        lot_id_by_code[str(r[1])] = int(r[0])

    assert "A_NEAR" in lot_id_by_code
    assert "B_FAR" in lot_id_by_code

    # 2) 准备 stocks_lot：同仓库、同品种，不同 lot 各 3 件
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty) VALUES
              (3003, 1, :lot_a, 3),
              (3003, 1, :lot_b, 3)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"lot_a": int(lot_id_by_code["A_NEAR"]), "lot_b": int(lot_id_by_code["B_FAR"])},
    )

    fa = FefoAllocator()
    plan = await fa.allocate(session, item_id=3003, need_qty=2, warehouse_id=1)

    assert len(plan) >= 1
    assert plan[0]["batch_code"] == "A_NEAR"
    assert int(plan[0]["take_qty"]) == 2
