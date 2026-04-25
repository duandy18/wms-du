# tests/unit/test_fefo_query_v2.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.shared.services.expiry_analytics_allocator import ExpiryAnalyticsAllocator
from app.wms.stock.services.lots import ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc


@pytest.mark.asyncio
async def test_expiry_analytics_query_returns_sorted_not_enforcing(session: AsyncSession):
    """
    Expiry analytics 查询 smoke（lot-world）：

    终态事实：
    - lots 承载 lot canonical snapshot（production_date / expiry_date）
    - RECEIPT stock_ledger 保留事件快照（production_date / expiry_date）
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

    now = datetime.now(UTC)
    prod = date.today()

    exp_near = prod + timedelta(days=1)
    exp_far = prod + timedelta(days=10)

    lot_near = await ensure_lot_full(
        session,
        item_id=3003,
        warehouse_id=1,
        lot_code="A_NEAR",
        production_date=prod,
        expiry_date=exp_near,
    )
    lot_far = await ensure_lot_full(
        session,
        item_id=3003,
        warehouse_id=1,
        lot_code="B_FAR",
        production_date=prod,
        expiry_date=exp_far,
    )

    # 用 lot-only 原语写入：RECEIPT 路径写 lot canonical snapshot + RECEIPT ledger snapshot
    # ref 必须不同，避免 ledger 唯一键冲突
    await adjust_lot_impl(
        session=session,
        warehouse_id=1,
        item_id=3003,
        lot_id=int(lot_near),
        delta=3,
        reason=MovementType.RECEIPT,
        ref="UT-EXP-NEAR",
        ref_line=1,
        occurred_at=now,
        meta=None,
        batch_code="A_NEAR",
        production_date=prod,
        expiry_date=exp_near,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )
    await adjust_lot_impl(
        session=session,
        warehouse_id=1,
        item_id=3003,
        lot_id=int(lot_far),
        delta=3,
        reason=MovementType.RECEIPT,
        ref="UT-EXP-FAR",
        ref_line=1,
        occurred_at=now,
        meta=None,
        batch_code="B_FAR",
        production_date=prod,
        expiry_date=exp_far,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )
    await session.commit()

    alloc = ExpiryAnalyticsAllocator()
    plan = await alloc.allocate(session, item_id=3003, need_qty=2, warehouse_id=1)

    assert len(plan) >= 1
    assert plan[0]["lot_code"] == "A_NEAR"
    assert int(plan[0]["take_qty"]) == 2
