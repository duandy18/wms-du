from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService


@pytest.mark.asyncio
async def test_available_decreases_when_open_reservation_exists(session: AsyncSession):
    """
    平台可售库存与 soft reserve 联动（扣减场景）：

    - 记录 baseline = available0
    - 插入一张 status='open' 的 reservation，qty=3
    - 再次查询 available1
    - 期望：available1 = available0 - 3
    """
    svc = ChannelInventoryService()

    platform = "PDD"
    shop_id = "SHOP1"
    warehouse_id = 1
    item_id = 3001
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 1) baseline
    available0 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )

    # 2) 插入一张 open reservation + 明细 qty=3
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, :ref,
                'open', now(), now(), :expire_at
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": "RSV-PLATFORM-1",
            "expire_at": now + timedelta(minutes=30),
        },
    )
    reservation_id = res.scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line,
                item_id, qty, consumed_qty,
                created_at, updated_at
            )
            VALUES (
                :rid, 1,
                :item_id, :qty, 0,
                now(), now()
            )
            """
        ),
        {
            "rid": reservation_id,
            "item_id": item_id,
            "qty": 3,
        },
    )

    await session.commit()

    # 3) 有 open reserve 后的 available
    available1 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )

    assert available1 == available0 - 3


@pytest.mark.asyncio
async def test_available_recovers_after_reservation_expired(session: AsyncSession):
    """
    平台可售库存与 soft reserve 联动（释放场景）：

    - baseline = available0
    - 插入一张 open reservation，qty=5
    - available1 = available0 - 5
    - 将该单 status 改为 'expired'（模拟 TTL 回收）
    - available2 应恢复为 available0
    """
    svc = ChannelInventoryService()

    platform = "PDD"
    shop_id = "SHOP1"
    warehouse_id = 1
    item_id = 3001

    # 1) baseline
    available0 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )

    # 2) 插入 open reservation
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, :ref,
                'open', now(), now(), now()
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": "RSV-PLATFORM-2",
        },
    )
    rid = res.scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line,
                item_id, qty, consumed_qty,
                created_at, updated_at
            )
            VALUES (
                :rid, 1,
                :item_id, :qty, 0,
                now(), now()
            )
            """
        ),
        {
            "rid": rid,
            "item_id": item_id,
            "qty": 5,
        },
    )
    await session.commit()

    # 3) 有 open reserve 时的 available
    available1 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    assert available1 == available0 - 5

    # 4) 模拟 TTL 或人工释放：open -> expired
    await session.execute(
        text(
            """
            UPDATE reservations
               SET status     = 'expired',
                   updated_at = now()
             WHERE id = :rid
            """
        ),
        {"rid": rid},
    )
    await session.commit()

    # 5) 再查 available，应恢复 baseline
    available2 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    assert available2 == available0


@pytest.mark.asyncio
async def test_available_ignores_consumed_reservations(session: AsyncSession):
    """
    消费完成的 reservation 不再占用平台可售库存：

    - baseline = available0
    - 插入一张 status='consumed' 的 reservation，qty=4，且 consumed_qty=4
    - 可售库存不应变化：available1 == available0
    """
    svc = ChannelInventoryService()

    platform = "PDD"
    shop_id = "SHOP1"
    warehouse_id = 1
    item_id = 3001

    available0 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )

    # 插入 consumed reservation
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, :ref,
                'consumed', now(), now(), NULL
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": "RSV-PLATFORM-3",
        },
    )
    rid = res.scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line,
                item_id, qty, consumed_qty,
                created_at, updated_at
            )
            VALUES (
                :rid, 1,
                :item_id, :qty, :qty,
                now(), now()
            )
            """
        ),
        {
            "rid": rid,
            "item_id": item_id,
            "qty": 4,
        },
    )
    await session.commit()

    available1 = await svc.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )

    # consumed 单既不被 status 条件选中，也在 qty-consumed_qty 维度上为 0
    assert available1 == available0
