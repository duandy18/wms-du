# tests/unit/test_fefo_query_v2.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_fallbacks import FefoAllocator
from tests.utils.ensure_minimal import ensure_item


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

    # Phase M：items policy NOT NULL + has_shelf_life CHECK → 统一走最小合法 helper
    await ensure_item(session, id=3003, sku="SKU-3003", name="ITEM-3003", expiry_required=True)

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
                    source_receipt_id,
                    source_line_no,
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    1,
                    3003,
                    'SUPPLIER',
                    v.lot_code,
                    NULL,
                    NULL,
                    CURRENT_DATE,
                    v.expiry_date,
                    'EXPLICIT',
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM (
                        VALUES
                          ('A_NEAR'::varchar, CURRENT_DATE + INTERVAL '1 day'),
                          ('B_FAR'::varchar,  CURRENT_DATE + INTERVAL '10 day')
                       ) AS v(lot_code, expiry_date)
                  JOIN items it ON it.id = 3003
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
