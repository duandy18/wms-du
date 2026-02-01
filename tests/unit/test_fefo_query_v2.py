# tests/unit/test_fefo_query_v2.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_fallbacks import FefoAllocator


@pytest.mark.asyncio
async def test_fefo_query_returns_sorted_not_enforcing(session: AsyncSession):
    """
    v2 FEFO 查询 smoke：

    - 同一仓库下，准备两个批次：
      * A_NEAR：expiry = +1 day
      * B_FAR ：expiry = +10 days
    - stocks 中各放 3 件；
    - 申请 need_qty=2；
    - 期望：
      * 计划列表中至少有一条；
      * 第一条来自 A_NEAR（最近到期优先）；
      * 第一条的 take_qty = 2（在最早批次中优先消耗）。
    """

    # 准备 batches（带 expiry_date）
    await session.execute(
        text(
            """
            INSERT INTO batches(item_id, warehouse_id, batch_code, expiry_date) VALUES
              (3003, 1, 'A_NEAR', CURRENT_DATE + INTERVAL '1 day'),
              (3003, 1, 'B_FAR',  CURRENT_DATE + INTERVAL '10 day')
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        )
    )

    # 准备 stocks：同仓库、同品种，不同批次各 3 件
    await session.execute(
        text(
            """
            INSERT INTO stocks(item_id, warehouse_id, batch_code, qty) VALUES
              (3003, 1, 'A_NEAR', 3),
              (3003, 1, 'B_FAR',  3)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch
            DO UPDATE SET qty = EXCLUDED.qty
            """
        )
    )

    fa = FefoAllocator()
    plan = await fa.allocate(session, item_id=3003, need_qty=2, warehouse_id=1)

    assert len(plan) >= 1

    first = plan[0]
    # v2：显式用 batch_code，而不是 batch_id
    assert first["batch_code"] == "A_NEAR"
    assert first["take_qty"] == 2
