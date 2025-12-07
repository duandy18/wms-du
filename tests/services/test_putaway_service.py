# tests/services/test_putaway_service.py
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# 测试辅助：按项目实际路径导入
from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code

from app.models.enums import MovementType
from app.services.putaway_service import PutawayService
from app.services.stock_service import StockService  # 直接入库以满足审计契约（带日期与批次码）

pytestmark = pytest.mark.grp_core


@pytest.mark.asyncio
async def test_putaway_binds_location_and_is_idempotent(session: AsyncSession):
    """
    Putaway 两腿：SRC→DST 搬 3；幂等：同 ref/left_ref_line 再次提交不变。
    审计契约对齐：
      - 出库（左腿，delta<0）：必须提供 batch_code
      - 入库（右腿，delta>0）：必须提供 batch_code 且提供 production_date 或 expiry_date（至少其一）
    """
    # 基线实体
    wh, src, dst, item, code = 1, 900, 1, 6006, "PA-DEMO-6006"
    await ensure_wh_loc_item(session, wh=wh, loc=src, item=item, code="SRC-900", name="SRC-900")
    await ensure_wh_loc_item(session, wh=wh, loc=dst, item=item, code="DST-001", name="DST-001")
    await session.commit()  # 造数完成

    # 入库 3（直接使用 StockService 以显式满足审计契约：批次码 + 日期）
    prod = date.today()
    exp = date.today() + timedelta(days=365)
    await session.commit()
    async with session.begin():
        _ = await StockService().adjust(
            session=session,
            item_id=item,
            location_id=src,
            delta=3,
            reason=MovementType.RECEIPT,
            ref="IN-PA",
            batch_code=code,
            production_date=prod,
            expiry_date=exp,
        )

    # 验证源位数量=3
    assert await qty_by_code(session, item=item, loc=src, code=code) == 3
    await session.commit()

    # Putaway：SRC→DST 搬 3（右腿为入库，需 production_date/expiry_date 至少其一）
    async with session.begin():
        res1 = await PutawayService().putaway(
            session=session,
            item_id=item,
            from_location_id=src,
            to_location_id=dst,
            qty=3,
            ref="PA-MV-1",
            batch_code=code,
            production_date=prod,
            expiry_date=exp,
            left_ref_line=1,  # 左腿=1，右腿=2
        )
    assert res1["moved"] == 3

    # 验证搬运后数量：源位=0，目标位=3
    await session.commit()
    assert await qty_by_code(session, item=item, loc=src, code=code) == 0
    assert await qty_by_code(session, item=item, loc=dst, code=code) == 3

    # 幂等：同 ref/left_ref_line 再次提交（左腿=1，右腿自动=2），应不变
    await session.commit()
    async with session.begin():
        _ = await PutawayService().putaway(
            session=session,
            item_id=item,
            from_location_id=src,
            to_location_id=dst,
            qty=3,
            ref="PA-MV-1",
            batch_code=code,
            production_date=prod,
            expiry_date=exp,
            left_ref_line=1,
        )

    await session.commit()
    assert await qty_by_code(session, item=item, loc=src, code=code) == 0
    assert await qty_by_code(session, item=item, loc=dst, code=code) == 3
