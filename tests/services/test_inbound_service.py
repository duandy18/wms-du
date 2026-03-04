# tests/services/test_inbound_service.py
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# 测试辅助：按项目实际路径导入
from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code

from app.models.enums import MovementType
from app.services.stock.lots import ensure_lot_full
from app.services.stock_service import StockService

UTC = timezone.utc
pytestmark = pytest.mark.grp_core


@pytest.mark.asyncio
async def test_inbound_creates_batch_and_increases_stock(session: AsyncSession):
    """
    入库：批次化落账 + 返回 on_hand_after（通过读数校验）
    事务边界：造数→commit；读后→commit；业务→begin
    审计契约：入库必须提供 batch_code 且 production_date 或 expiry_date 至少其一

    Phase 4D：
    - 库存真相在 stocks_lot（lot-world），因此本用例改为：
      * 先创建 SUPPLIER lot（lot_code=code）
      * 再用 StockService.adjust_lot 入库（写 stocks_lot + ledger(lot_id)）
      * 最终用 qty_by_code（lot-world 口径）断言 qty=6

    Phase M-3：
    - items.case_ratio/case_uom 已删除；lots 不再承载 item_case_*_snapshot / item_uom_snapshot 等历史残影列
    - lots 也不再承载 production_date/expiry_date/expiry_source（日期事实在 receipt/ledger 侧表达）
    """
    wh, loc, item, code = 1, 1, 5001, "INB-DEMO-BATCH"

    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await session.commit()

    ref = f"IN-{int(datetime.now(UTC).timestamp())}"
    exp = date.today() + timedelta(days=365)

    # ✅ 终态：supplier lot 必须走 ensure_lot_full（lot_code_key + partial unique index）
    lot_id = await ensure_lot_full(
        session,
        item_id=int(item),
        warehouse_id=int(wh),
        lot_code=str(code),
        production_date=None,
        expiry_date=None,
    )

    await session.commit()
    async with session.begin():
        _ = await StockService().adjust_lot(
            session=session,
            item_id=item,
            warehouse_id=wh,
            lot_id=int(lot_id),
            delta=6,
            reason=MovementType.RECEIPT,
            ref=ref,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=exp,
        )

    await session.commit()
    assert await qty_by_code(session, item=item, loc=loc, code=code) == 6
