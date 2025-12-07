from datetime import datetime

import pytest
from sqlalchemy import text

from app.services.reservation_service import ReservationError, ReservationService
from app.services.store_service import StoreService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_reserve_by_warehouse_or_default(session):
    # 准备：两个仓
    await session.execute(
        text("INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
    )
    await session.execute(
        text("INSERT INTO warehouses (id,name) VALUES (2,'WH-2') ON CONFLICT (id) DO NOTHING")
    )
    await session.commit()

    # 为店绑定默认仓1
    store_id = await StoreService.ensure_store(
        session, platform="PDD", shop_id="RZ-SHOP-01", name="RZ-店1"
    )
    await StoreService.bind_warehouse(
        session, store_id=store_id, warehouse_id=1, is_default=True, priority=10
    )
    await session.commit()

    # 1) 不指定 warehouse_id，走默认仓
    plan1 = await ReservationService.reserve(
        session,
        platform="PDD",
        shop_id="RZ-SHOP-01",
        ref="UT-RZ-001",
        lines=[{"item_id": 1001, "qty": 2}, {"item_id": 1002, "qty": 3}],
    )
    assert plan1["status"] == "OK"
    assert plan1["warehouse_id"] == 1
    assert len(plan1["plan"]) == 2
    assert all(it["warehouse_id"] == 1 and it["batch_id"] is None for it in plan1["plan"])

    # 2) 指定另一个仓（覆盖默认仓）
    plan2 = await ReservationService.reserve(
        session,
        platform="PDD",
        shop_id="RZ-SHOP-01",
        ref="UT-RZ-002",
        lines=[{"item_id": 1001, "qty": 1}],
        warehouse_id=2,
    )
    assert plan2["warehouse_id"] == 2
    assert plan2["plan"][0]["item_id"] == 1001
    assert plan2["plan"][0]["qty"] == 1

    # 3) 幂等（相同输入返回相同计划；本实现为纯函数式）
    again = await ReservationService.reserve(
        session,
        platform="PDD",
        shop_id="RZ-SHOP-01",
        ref="UT-RZ-002",
        lines=[{"item_id": 1001, "qty": 1}],
        warehouse_id=2,
    )
    assert again == plan2

    # 4) 无默认仓且未传 warehouse_id → 抛 ReservationError
    store_id2 = await StoreService.ensure_store(
        session, platform="PDD", shop_id="RZ-NODEF-01", name="无默认仓店"
    )
    await session.commit()
    with pytest.raises(ReservationError):
        await ReservationService.reserve(
            session,
            platform="PDD",
            shop_id="RZ-NODEF-01",
            ref="UT-RZ-003",
            lines=[{"item_id": 1001, "qty": 1}],
        )

    # 5) 不应有任何 ledger 写入（PICK 之前不落账）
    cnt = (
        await session.execute(text("SELECT COUNT(*) FROM stock_ledger WHERE reason='PICK'"))
    ).scalar() or 0
    assert cnt == 0
