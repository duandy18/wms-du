# tests/services/test_inbound_service.py
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# 测试辅助：按项目实际路径导入
from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc
pytestmark = pytest.mark.grp_core


@pytest.mark.asyncio
async def test_inbound_creates_batch_and_increases_stock(session: AsyncSession):
    """
    入库：批次化落账 + 返回 on_hand_after（通过读数校验）
    事务边界：造数→commit；读后→commit；业务→begin
    审计契约：入库必须提供 batch_code 且 production_date 或 expiry_date 至少其一

    v2 版本下，库存粒度为 (warehouse_id, item_id, batch_code)，
    因此这里用 wh 作为唯一的仓库维度；loc 仍然保留给测试工具 ensure_wh_loc_item/qty_by_code 使用。
    """
    wh, loc, item, code = 1, 1, 5001, "INB-DEMO-BATCH"

    # 造数：仓库/库位/商品（测试工具内部仍使用 loc 维度造底层数据）
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await session.commit()  # 造数完成，关闭隐式事务

    # 入库 6（提供 batch_code + expiry_date 满足审计契约）
    ref = f"IN-{int(datetime.now(UTC).timestamp())}"
    exp = date.today() + timedelta(days=365)

    await session.commit()  # 防止外层隐式事务
    async with session.begin():
        _ = await StockService().adjust(
            session=session,
            item_id=item,
            warehouse_id=wh,  # ✅ v2：以仓库为主维度，不再传 location_id
            delta=6,
            reason=MovementType.RECEIPT,
            ref=ref,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=exp,  # 传有效期（或传 production_date 亦可）
        )

    # 校验：批次化落账，on_hand_after == 6
    await session.commit()
    assert await qty_by_code(session, item=item, loc=loc, code=code) == 6
