from datetime import datetime

import pytest
from sqlalchemy import text

from app.services.reservation_service import ReservationError, ReservationService
from app.services.store_service import StoreService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_reserve_by_warehouse_or_default(session):
    # 准备：两个仓
    await session.execute(text("INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO warehouses (id,name) VALUES (2,'WH-2') ON CONFLICT (id) DO NOTHING"))
    await session.commit()

    # 为店绑定默认仓1（历史配置允许存在，但 Route C 合同下 reserve 不允许依赖默认仓兜底）
    store_id = await StoreService.ensure_store(session, platform="PDD", shop_id="RZ-SHOP-01", name="RZ-店1")
    await StoreService.bind_warehouse(session, store_id=store_id, warehouse_id=1, is_default=True, priority=10)
    await session.commit()

    # 1) Route C 合同：不允许默认仓兜底，未传 warehouse_id 必须抛 ReservationError
    with pytest.raises(ReservationError):
        await ReservationService.reserve(
            session,
            platform="PDD",
            shop_id="RZ-SHOP-01",
            ref="UT-RZ-001",
            lines=[{"item_id": 1001, "qty": 2}, {"item_id": 1002, "qty": 3}],
        )

    # 2) 显式指定 warehouse_id（等价于“指明履约约束”）
    plan1 = await ReservationService.reserve(
        session,
        platform="PDD",
        shop_id="RZ-SHOP-01",
        ref="UT-RZ-001",
        lines=[{"item_id": 1001, "qty": 2}, {"item_id": 1002, "qty": 3}],
        warehouse_id=1,
    )
    assert plan1["status"] == "OK"
    assert plan1["warehouse_id"] == 1
    assert len(plan1["plan"]) == 2
    assert all(it["warehouse_id"] == 1 and it["batch_id"] is None for it in plan1["plan"])

    # 3) 指定另一个仓（覆盖默认仓）
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

    # 4) 幂等（相同输入返回相同计划；本实现为纯函数式）
    again = await ReservationService.reserve(
        session,
        platform="PDD",
        shop_id="RZ-SHOP-01",
        ref="UT-RZ-002",
        lines=[{"item_id": 1001, "qty": 1}],
        warehouse_id=2,
    )
    assert again == plan2

    # 5) 无默认仓且未传 warehouse_id → 抛 ReservationError
    _ = await StoreService.ensure_store(session, platform="PDD", shop_id="RZ-NODEF-01", name="无默认仓店")
    await session.commit()
    with pytest.raises(ReservationError):
        await ReservationService.reserve(
            session,
            platform="PDD",
            shop_id="RZ-NODEF-01",
            ref="UT-RZ-003",
            lines=[{"item_id": 1001, "qty": 1}],
        )

    # 6) 不应有任何 ledger 写入（PICK 之前不落账）
    cnt = (await session.execute(text("SELECT COUNT(*) FROM stock_ledger WHERE reason='PICK'"))).scalar() or 0
    assert cnt == 0
