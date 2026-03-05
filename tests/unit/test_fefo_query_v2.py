# tests/unit/test_fefo_query_v2.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.expiry_analytics_allocator import ExpiryAnalyticsAllocator
from app.services.stock_service import StockService
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc


@pytest.mark.asyncio
async def test_expiry_analytics_query_returns_sorted_not_enforcing(session: AsyncSession):
    """
    Expiry analytics 查询 smoke（lot-world）：

    终态事实：
    - lots 只承载 identity（lot_code）
    - 时间事实（production_date/expiry_date）在 stock_ledger（reason_canon='RECEIPT'）
    - 余额事实在 stocks_lot

    测试：
    - 同一仓库下，准备两个 lot：
      * A_NEAR：expiry = +1 day
      * B_FAR ：expiry = +10 days
    - 各入库 3 件（写 ledger + stocks_lot）
    - 申请 need_qty=2；
    - 期望：
      * 计划列表中至少有一条；
      * 第一条来自 A_NEAR（最近到期优先）；
      * 第一条的 take_qty = 2（在最早批次中优先消耗）。
    """
    await ensure_item(session, id=3003, sku="SKU-3003", name="ITEM-3003", expiry_required=True)

    svc = StockService()
    now = datetime.now(UTC)
    prod = date.today()

    exp_near = prod + timedelta(days=1)
    exp_far = prod + timedelta(days=10)

    # 用正路写入：reason_canon='RECEIPT' 的台账行允许携带 production/expiry
    # ref 必须不同，避免 ledger 唯一键冲突
    await svc.adjust(
        session=session,
        warehouse_id=1,
        item_id=3003,
        delta=3,
        reason=MovementType.RECEIPT,
        ref="UT-EXP-NEAR",
        ref_line=1,
        occurred_at=now,
        batch_code="A_NEAR",
        production_date=prod,
        expiry_date=exp_near,
    )
    await svc.adjust(
        session=session,
        warehouse_id=1,
        item_id=3003,
        delta=3,
        reason=MovementType.RECEIPT,
        ref="UT-EXP-FAR",
        ref_line=1,
        occurred_at=now,
        batch_code="B_FAR",
        production_date=prod,
        expiry_date=exp_far,
    )
    await session.commit()

    alloc = ExpiryAnalyticsAllocator()
    plan = await alloc.allocate(session, item_id=3003, need_qty=2, warehouse_id=1)

    assert len(plan) >= 1
    assert plan[0]["batch_code"] == "A_NEAR"
    assert int(plan[0]["take_qty"]) == 2
