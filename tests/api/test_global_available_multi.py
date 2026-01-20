from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.services.soft_reserve_service import SoftReserveService

pytestmark = pytest.mark.asyncio


async def test_channel_inventory_multi_basic(client, session: AsyncSession):
    """
    多仓可售视图基础验证：

    - WH1: on_hand >= 3, open reservation = 3 → available = max(on_hand - 3, 0)
    - WH2: on_hand >= 5, open reservation = 0 → available = on_hand

    我们不对绝对 on_hand 值做强约束（helpers 可能预置基线库存），
    只验证“锁住 3 后，可售 = on_hand - 3”的关系是否成立。
    """
    platform = "PDD"
    shop_id = "S-MULTI"
    item_id = 3003

    # 仓 1 和 仓 2 建立基础 item/批次/库存
    await ensure_wh_loc_item(session, wh=1, loc=1, item=item_id)
    await ensure_wh_loc_item(session, wh=2, loc=2, item=item_id)

    # WH1: 再加一批 10 货，WH2: 再加一批 5 货
    await seed_batch_slot(session, item=item_id, loc=1, code="B-W1", qty=10, days=365)
    await seed_batch_slot(session, item=item_id, loc=2, code="B-W2", qty=5, days=365)

    # WH1 上锁 3 个（open reservation）
    soft = SoftReserveService()
    await soft.persist(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=1,
        ref="MULTI-RESV-1",
        lines=[{"item_id": item_id, "qty": 3}],
    )

    await session.commit()

    # 调用多仓可售 API
    resp = await client.get(f"/global-available/{platform}/{shop_id}/item/{item_id}")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["platform"] == platform
    assert data["shop_id"] == shop_id
    assert data["item_id"] == item_id

    warehouses = sorted(data["warehouses"], key=lambda w: w["warehouse_id"])
    # 预期至少包含两个仓
    w_ids = [w["warehouse_id"] for w in warehouses]
    assert 1 in w_ids and 2 in w_ids

    # 拿出 wh1, wh2 的视图
    w1 = next(w for w in warehouses if w["warehouse_id"] == 1)
    w2 = next(w for w in warehouses if w["warehouse_id"] == 2)

    # WH1：锁了 3 个
    assert w1["reserved_open"] == 3
    # on_hand 至少 >= 3（否则测试本身造数有问题）
    assert w1["on_hand"] >= 3
    # available 必须符合 max(on_hand - 3, 0)
    assert w1["available"] == max(w1["on_hand"] - 3, 0)

    # WH2：没有锁量
    assert w2["reserved_open"] == 0
    # on_hand 至少 >= 5（我们刚 seed 了一批 5）
    assert w2["on_hand"] >= 5
    # available 必须等于 on_hand
    assert w2["available"] == w2["on_hand"]

    # 批次明细不做强约束，只要求至少有一条
    assert len(w1["batches"]) >= 1
    assert len(w2["batches"]) >= 1
