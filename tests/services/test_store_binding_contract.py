import pytest
from sqlalchemy import text

from app.services.store_service import StoreService

pytestmark = pytest.mark.asyncio

PLATS = ["PDD", "TAOBAO", "TMALL", "JD", "RED", "DOUYIN", "AMAZON", "TEMU", "SHOPIFY", "ALIEXPRESS"]


@pytest.mark.asyncio
async def test_store_auto_upsert_and_bind_multi_warehouses(session):
    # 前置：确保有两个仓
    await session.execute(
        text("INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
    )
    await session.execute(
        text("INSERT INTO warehouses (id,name) VALUES (2,'WH-2') ON CONFLICT (id) DO NOTHING")
    )
    await session.commit()

    # 为每个平台插两个店并绑定两个仓（其中一个默认）
    for i, plat in enumerate(PLATS, start=1):
        shop = f"SHOP-{i:02d}"
        sid = await StoreService.ensure_store(
            session, platform=plat, shop_id=shop, name=f"{plat}-{shop}"
        )
        await StoreService.bind_warehouse(
            session, store_id=sid, warehouse_id=1, is_default=True, priority=10
        )
        await StoreService.bind_warehouse(
            session, store_id=sid, warehouse_id=2, is_default=False, priority=50
        )
    await session.commit()

    # 抽查一个平台，验证默认仓选择
    sid_row = await session.execute(
        text("SELECT id FROM stores WHERE platform='PDD' AND shop_id='SHOP-01'")
    )
    sid = sid_row.scalar_one()
    wh = await StoreService.resolve_default_warehouse(session, store_id=sid)
    assert wh == 1

    # 绑定表幂等：重复绑定不报错
    await StoreService.bind_warehouse(
        session, store_id=sid, warehouse_id=1, is_default=True, priority=5
    )
    await session.commit()
    row = (
        await session.execute(
            text(
                """
        SELECT priority FROM store_warehouse WHERE store_id=:sid AND warehouse_id=1
    """
            ),
            {"sid": sid},
        )
    ).first()
    assert row and row[0] == 5
