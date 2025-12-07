from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.soft_reserve_ttl import sweep_soft_reserve_ttl


@pytest.mark.asyncio
async def test_ttl_expired_open_reservations_are_marked_expired(session: AsyncSession):
    """
    场景：
      - 一张已过期且 status='open' 的 reservation
      - 一张未过期的 reservation（或 expire_at 为 None）

    期望：
      - 过期的那张被标记为 'expired'
      - 未过期的保持 'open'
      - sweep 返回 1
    """
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 1) 插入一张已过期的 open reservation
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                'PDD', 'SHOP1', 1, 'RSV-EXPIRED-1',
                'open', now(), now(), :expired_at
            )
            RETURNING id
            """
        ),
        {"expired_at": now - timedelta(minutes=5)},
    )
    expired_id = res.scalar_one()

    # 2) 插入一张未过期的 open reservation
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                'PDD', 'SHOP1', 1, 'RSV-FUTURE-1',
                'open', now(), now(), :expire_at
            )
            RETURNING id
            """
        ),
        {"expire_at": now + timedelta(minutes=30)},
    )
    future_id = res.scalar_one()

    # 3) 给两张单都塞一条明细（虽然 TTL 不动行，但保持结构完整）
    for rid, item_id, qty in [
        (expired_id, 3001, 2),
        (future_id, 3001, 3),
    ]:
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
            {"rid": rid, "item_id": item_id, "qty": qty},
        )

    await session.commit()

    # 4) 跑 TTL 扫描
    expired_count = await sweep_soft_reserve_ttl(
        session,
        now=now,
        batch_size=10,
        reason="expired",
    )

    assert expired_count == 1

    # 5) 校验状态
    res = await session.execute(
        text(
            """
            SELECT id, status
            FROM reservations
            WHERE id IN (:expired_id, :future_id)
            ORDER BY id
            """
        ),
        {"expired_id": expired_id, "future_id": future_id},
    )
    rows = {int(r[0]): r[1] for r in res.fetchall()}

    assert rows[expired_id] == "expired"
    assert rows[future_id] == "open"


@pytest.mark.asyncio
async def test_ttl_sweep_is_idempotent(session: AsyncSession):
    """
    场景：
      - 一张已过期 open reservation
      - 连续调用两次 sweep_soft_reserve_ttl

    期望：
      - 首次：返回 1，status 从 'open' -> 'expired'
      - 第二次：返回 0，status 仍是 'expired'，不会回滚或重复改写
    """
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 1) 插入一张过期的 open reservation
    res = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                'PDD', 'SHOP1', 1, 'RSV-IDEMP-1',
                'open', now(), now(), :expired_at
            )
            RETURNING id
            """
        ),
        {"expired_at": now - timedelta(minutes=10)},
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
                3001, 5, 0,
                now(), now()
            )
            """
        ),
        {"rid": rid},
    )
    await session.commit()

    # 2) 第一次 TTL 扫描
    c1 = await sweep_soft_reserve_ttl(session, now=now, batch_size=10)
    assert c1 == 1

    # 3) 第二次 TTL 扫描（幂等）
    c2 = await sweep_soft_reserve_ttl(session, now=now, batch_size=10)
    assert c2 == 0

    # 4) 状态保持为 expired
    res = await session.execute(
        text("SELECT status FROM reservations WHERE id = :rid"),
        {"rid": rid},
    )
    status = res.scalar_one()
    assert status == "expired"


@pytest.mark.asyncio
async def test_ttl_respects_batch_size(session: AsyncSession):
    """
    场景：
      - 插入多张过期 open reservations
      - 设置 batch_size < 总数

    期望：
      - 一次 sweep 只处理 batch_size 张（由于 while 循环 + LIMIT，每轮最多 batch_size）
      - 但我们的实现中会在 while 中继续下一轮，直到跑完所有候选，
        所以最终结果应该是全部处理掉。
      - 本测试主要确认“多轮扫描 + 批次处理”逻辑不会丢单。
    """
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 插入 3 张过期 open reservations
    ids = []
    for i in range(3):
        res = await session.execute(
            text(
                """
                INSERT INTO reservations (
                    platform, shop_id, warehouse_id, ref,
                    status, created_at, updated_at, expire_at
                )
                VALUES (
                    'PDD', 'SHOP1', 1, :ref,
                    'open', now(), now(), :expired_at
                )
                RETURNING id
                """
            ),
            {
                "ref": f"RSV-BATCH-{i + 1}",
                "expired_at": now - timedelta(minutes=5 + i),
            },
        )
        ids.append(res.scalar_one())

    await session.commit()

    # batch_size = 2，小于 3；预期三张都被处理
    expired_count = await sweep_soft_reserve_ttl(
        session,
        now=now,
        batch_size=2,
    )
    assert expired_count == 3

    res = await session.execute(
        text(
            """
            SELECT COUNT(*) FROM reservations
            WHERE id = ANY(:ids) AND status = 'expired'
            """
        ),
        {"ids": ids},
    )
    cnt_expired = res.scalar_one()
    assert cnt_expired == 3
