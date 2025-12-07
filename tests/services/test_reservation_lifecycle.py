from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services.reservation_service import ReservationError, ReservationService  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _seed_dimensions(
    session,
    *,
    warehouse_id: int = 1,
    item_id: int = 1001,
) -> None:
    """
    为 ReservationService 准备最小维度数据：
    - warehouses.id
    - items.id

    由于 reservation_lines.item_id 很可能有外键指向 items.id，
    我们提前插好维度，避免外键约束炸掉。
    """
    # 仓库
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:w, 'WH-TEST')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"w": warehouse_id},
    )

    # 货品
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:i, 'UT-ITEM', 'ITEM-TEST')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"i": item_id},
    )

    await session.commit()


@pytest.mark.asyncio
async def test_persist_creates_and_is_idempotent(session):
    """
    persist 行为验证：

    - 首次调用：插入一条 reservations + 若干 reservation_lines；
    - 再次调用（同 platform/shop/wh/ref）：应复用同一 reservation_id，
      并更新行的 qty（覆盖原值），保证“业务键”幂等。
    """
    svc = ReservationService()
    platform, shop = "PDD", "SHOP-RZ-1"
    wh, item = 1, 1001
    ref = "RZ-PERSIST-001"

    await _seed_dimensions(session, warehouse_id=wh, item_id=item)

    # 第一次 persist
    r1 = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=wh,
        ref=ref,
        lines=[{"item_id": item, "qty": 2}],
        expire_at=30,  # 30 分钟后过期
    )
    rid1 = r1["reservation_id"]
    assert r1["status"] == "OK"
    assert isinstance(rid1, int)

    # 校验头表
    row = await session.execute(
        text(
            """
            SELECT platform, shop_id, warehouse_id, ref, status
              FROM reservations
             WHERE id = :rid
            """
        ),
        {"rid": rid1},
    )
    platform_db, shop_db, wh_db, ref_db, status_db = row.one()
    assert platform_db == platform
    assert shop_db == shop
    assert wh_db == wh
    assert ref_db == ref
    assert status_db == "open"

    # 校验明细
    lines = await svc.get_lines(session, reservation_id=rid1)
    # get_lines 返回 (item_id, qty) 列表
    assert lines == [(item, 2)]

    # 第二次 persist：相同业务键，但 qty 改为 5
    r2 = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=wh,
        ref=ref,
        lines=[{"item_id": item, "qty": 5}],
        expire_at=60,  # 更新过期时间
    )
    rid2 = r2["reservation_id"]
    assert r2["status"] == "OK"
    assert rid2 == rid1  # 业务键幂等：id 不变

    # 再查明细，数量应被更新为 5
    lines2 = await svc.get_lines(session, reservation_id=rid1)
    assert lines2 == [(item, 5)]


@pytest.mark.asyncio
async def test_mark_consumed_sets_status_and_consumed_qty(session):
    """
    mark_consumed 行为验证：

    - 将所有 reservation_lines.consumed_qty 设置为 qty；
    - 将 reservations.status 设置为 'consumed'；
    - 不创建新行，只是就地更新。
    """
    svc = ReservationService()
    platform, shop = "PDD", "SHOP-RZ-2"
    wh, item = 1, 1001
    ref = "RZ-CONSUMED-001"

    await _seed_dimensions(session, warehouse_id=wh, item_id=item)

    # 先持久化一张 open 订单，qty=3
    r = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=wh,
        ref=ref,
        lines=[{"item_id": item, "qty": 3}],
        expire_at=None,
    )
    rid = r["reservation_id"]

    # 调用 mark_consumed
    await svc.mark_consumed(session, reservation_id=rid)
    await session.commit()

    # 头表状态应为 consumed
    row = await session.execute(
        text("SELECT status FROM reservations WHERE id = :rid"),
        {"rid": rid},
    )
    status_db = row.scalar()
    assert status_db == "consumed"

    # 明细 consumed_qty 应等于 qty
    row_lines = await session.execute(
        text(
            """
            SELECT qty, consumed_qty
              FROM reservation_lines
             WHERE reservation_id = :rid
            """
        ),
        {"rid": rid},
    )
    qty_db, consumed_db = row_lines.one()
    assert int(qty_db) == 3
    assert int(consumed_db) == 3


@pytest.mark.asyncio
async def test_mark_released_sets_status_to_reason(session):
    """
    mark_released 行为验证：

    - 将 reservations.status 更新为给定 reason（例如 'expired'）；
    - 不修改明细行；
    - 用于 TTL worker / 取消等场景的终结状态。
    """
    svc = ReservationService()
    platform, shop = "PDD", "SHOP-RZ-3"
    wh, item = 1, 1001
    ref = "RZ-RELEASED-001"

    await _seed_dimensions(session, warehouse_id=wh, item_id=item)

    r = await svc.persist(
        session,
        platform=platform,
        shop_id=shop,
        warehouse_id=wh,
        ref=ref,
        lines=[{"item_id": item, "qty": 1}],
        expire_at=10,
    )
    rid = r["reservation_id"]

    # 先确认初始状态是 open
    row0 = await session.execute(
        text("SELECT status FROM reservations WHERE id = :rid"),
        {"rid": rid},
    )
    assert row0.scalar() == "open"

    # 标记为 expired
    await svc.mark_released(session, reservation_id=rid, reason="expired")
    await session.commit()

    row1 = await session.execute(
        text("SELECT status FROM reservations WHERE id = :rid"),
        {"rid": rid},
    )
    assert row1.scalar() == "expired"


@pytest.mark.asyncio
async def test_find_expired_returns_only_open_and_past(session):
    """
    find_expired 行为验证：

    - 只返回 status='open' 且 expire_at < now 的 reservation.id；
    - 已被 mark_released / mark_consumed 的记录不能再被找出来；
    - 未设置 expire_at 的 open 记录不在结果中。
    """
    svc = ReservationService()
    platform, shop = "PDD", "SHOP-RZ-4"
    wh, item = 1, 1001

    await _seed_dimensions(session, warehouse_id=wh, item_id=item)

    # 用 Python UTC-aware 时间，保持与数据库 timestamptz 一致
    now = datetime.now(timezone.utc)

    expired_open_at = now - timedelta(minutes=10)
    future_open_at = now + timedelta(minutes=10)
    expired_consumed_at = now - timedelta(minutes=20)

    # 1) open, 已过期
    row_expired_open = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, 'RZ-EXPIRED-OPEN',
                'open', :created_at, :updated_at, :expire_at
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop,
            "warehouse_id": wh,
            "created_at": now,
            "updated_at": now,
            "expire_at": expired_open_at,
        },
    )
    rid_expired_open = row_expired_open.scalar_one()

    # 2) open, 未来才过期
    row_future_open = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, 'RZ-FUTURE-OPEN',
                'open', :created_at, :updated_at, :expire_at
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop,
            "warehouse_id": wh,
            "created_at": now,
            "updated_at": now,
            "expire_at": future_open_at,
        },
    )
    rid_future_open = row_future_open.scalar_one()

    # 3) consumed, 已过期
    row_expired_consumed = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, 'RZ-EXPIRED-CONSUMED',
                'consumed', :created_at, :updated_at, :expire_at
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop,
            "warehouse_id": wh,
            "created_at": now,
            "updated_at": now,
            "expire_at": expired_consumed_at,
        },
    )
    rid_expired_consumed = row_expired_consumed.scalar_one()

    assert rid_expired_open != rid_future_open != rid_expired_consumed

    await session.commit()

    # 调用 find_expired：应该只返回 rid_expired_open
    expired_ids = await svc.find_expired(session, now=now, limit=10)
    assert rid_expired_open in expired_ids
    assert rid_future_open not in expired_ids
    assert rid_expired_consumed not in expired_ids
