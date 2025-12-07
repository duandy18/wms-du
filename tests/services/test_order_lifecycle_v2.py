# tests/services/test_order_lifecycle_v2.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_lifecycle_v2 import OrderLifecycleV2Service

pytestmark = pytest.mark.asyncio


async def _seed_full_lifecycle_case(session: AsyncSession) -> str:
    """
    构造一个“正常履约 + 退货”的生命周期场景：

    - trace_id = 'LIFE-UT-1'
    - orders: 一条
    - reservations + reservation_lines: 预占 qty=2, consumed_qty=2
    - stock_ledger:
        * RESERVE delta=+2
        * SHIPMENT delta=-2
        * RETURN_IN delta=+1
    - outbound_commits_v2: 一条 COMMITTED（如已有记录则跳过）
    - audit_events: 一条 flow=OUTBOUND（兜底）
    """
    trace_id = "LIFE-UT-1"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4001
    ext_order_no = "UT-ORDER-1"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    # items
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "item_id": item_id,
            "sku": f"UT-SKU-{item_id}",
            "name": f"UT-Item-{item_id}",
        },
    )

    # orders
    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform, shop_id, ext_order_no,
                warehouse_id, status, trace_id, created_at, updated_at
            )
            VALUES (
                :platform, :shop_id, :ext_order_no,
                :wh_id, 'CREATED', :trace_id, now(), now()
            )
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ext_order_no": ext_order_no,
            "wh_id": wh_id,
            "trace_id": trace_id,
        },
    )
    order_id = int(row.scalar_one())
    assert order_id > 0

    # reservations 头（幂等：基于 uq_reservations_platform_shop_wh_ref）
    row = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id,
                ref, status, created_at, updated_at,
                expire_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :wh_id,
                :ref, 'open', now(), now(),
                now() + INTERVAL '1 hour', :trace_id
            )
            ON CONFLICT ON CONSTRAINT uq_reservations_platform_shop_wh_ref
            DO UPDATE
               SET trace_id   = EXCLUDED.trace_id,
                   updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "wh_id": wh_id,
            "ref": order_ref,
            "trace_id": trace_id,
        },
    )
    rid = int(row.scalar_one())

    # reservation_lines（幂等：基于 ix_reservation_lines_res_refline）
    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line, item_id,
                qty, consumed_qty, created_at, updated_at
            )
            VALUES (
                :rid, 1, :item_id,
                2, 2, now(), now()
            )
            ON CONFLICT ON CONSTRAINT ix_reservation_lines_res_refline
            DO UPDATE
               SET qty          = EXCLUDED.qty,
                   consumed_qty = EXCLUDED.consumed_qty,
                   updated_at   = now()
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    # outbound_commits_v2（如已有相同 platform/shop/ref，则跳过）
    await session.execute(
        text(
            """
            INSERT INTO outbound_commits_v2 (
                platform, shop_id, ref, state, created_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :ref, 'COMMITTED', now(), :trace_id
            )
            ON CONFLICT (platform, shop_id, ref) DO NOTHING
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ref": order_ref,
            "trace_id": trace_id,
        },
    )

    # audit_events flow=OUTBOUND（兜底）
    await session.execute(
        text(
            """
            INSERT INTO audit_events (
                trace_id, category, ref, meta, created_at
            )
            VALUES (
                :trace_id, 'outbound_flow', :ref,
                jsonb_build_object('flow', 'OUTBOUND'),
                now()
            )
            """
        ),
        {"trace_id": trace_id, "ref": order_ref},
    )

    # stock_ledger：RESERVE / SHIPMENT / RETURN_IN
    await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
                trace_id,
                warehouse_id,
                item_id,
                batch_code,
                reason,
                ref,
                ref_line,
                delta,
                occurred_at,
                created_at,
                after_qty
            )
            VALUES
            (
                :trace_id,
                :wh_id,
                :item_id,
                'B-LIFE-1',
                'RESERVE',
                :ref,
                1,
                2,
                now(),
                now(),
                2
            ),
            (
                :trace_id,
                :wh_id,
                :item_id,
                'B-LIFE-1',
                'SHIPMENT',
                :ref,
                1,
                -2,
                now() + INTERVAL '5 min',
                now() + INTERVAL '5 min',
                0
            ),
            (
                :trace_id,
                :wh_id,
                :item_id,
                'B-LIFE-1',
                'RETURN_IN',
                :ref,
                1,
                1,
                now() + INTERVAL '20 min',
                now() + INTERVAL '20 min',
                1
            )
            """
        ),
        {
            "trace_id": trace_id,
            "wh_id": wh_id,
            "item_id": item_id,
            "ref": order_ref,
        },
    )

    await session.commit()
    return trace_id


async def _seed_missing_shipped_case(session: AsyncSession) -> str:
    """
    构造一个“只有预占，没有发货”的生命周期场景：
    """
    trace_id = "LIFE-UT-2"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4002
    ext_order_no = "UT-ORDER-2"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    # items
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "item_id": item_id,
            "sku": f"UT-SKU-{item_id}",
            "name": f"UT-Item-{item_id}",
        },
    )

    # orders
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform, shop_id, ext_order_no,
                warehouse_id, status, trace_id, created_at, updated_at
            )
            VALUES (
                :platform, :shop_id, :ext_order_no,
                :wh_id, 'CREATED', :trace_id, now(), now()
            )
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ext_order_no": ext_order_no,
            "wh_id": wh_id,
            "trace_id": trace_id,
        },
    )

    # reservations（幂等）
    row = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id,
                ref, status, created_at, updated_at,
                expire_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :wh_id,
                :ref, 'open', now(), now(),
                now() + INTERVAL '1 hour', :trace_id
            )
            ON CONFLICT ON CONSTRAINT uq_reservations_platform_shop_wh_ref
            DO UPDATE
               SET trace_id   = EXCLUDED.trace_id,
                   updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "wh_id": wh_id,
            "ref": order_ref,
            "trace_id": trace_id,
        },
    )
    rid = int(row.scalar_one())

    # reservation_lines（幂等）
    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line, item_id,
                qty, consumed_qty, created_at, updated_at
            )
            VALUES (
                :rid, 1, :item_id,
                2, 0, now(), now()
            )
            ON CONFLICT ON CONSTRAINT ix_reservation_lines_res_refline
            DO UPDATE
               SET qty          = EXCLUDED.qty,
                   consumed_qty = EXCLUDED.consumed_qty,
                   updated_at   = now()
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    # outbound 存在，但没有任何 SHIP 类型 ledger
    await session.execute(
        text(
            """
            INSERT INTO outbound_commits_v2 (
                platform, shop_id, ref, state, created_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :ref, 'COMMITTED', now(), :trace_id
            )
            ON CONFLICT (platform, shop_id, ref) DO NOTHING
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ref": order_ref,
            "trace_id": trace_id,
        },
    )

    await session.commit()
    return trace_id


async def _seed_reserve_only_case(session: AsyncSession) -> str:
    """
    构造一个“只有预占，没有消耗 / 出库 / 发货 / 退货”的生命周期场景：
    """
    trace_id = "LIFE-UT-3"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4003
    ext_order_no = "UT-ORDER-3"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    # items
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "item_id": item_id,
            "sku": f"UT-SKU-{item_id}",
            "name": f"UT-Item-{item_id}",
        },
    )

    # 订单头
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform, shop_id, ext_order_no,
                warehouse_id, status, trace_id, created_at, updated_at
            )
            VALUES (
                :platform, :shop_id, :ext_order_no,
                :wh_id, 'CREATED', :trace_id, now(), now()
            )
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ext_order_no": ext_order_no,
            "wh_id": wh_id,
            "trace_id": trace_id,
        },
    )

    # reservation 头（幂等）
    row = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id,
                ref, status, created_at, updated_at,
                expire_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :wh_id,
                :ref, 'open', now(), now(),
                now() + INTERVAL '1 hour', :trace_id
            )
            ON CONFLICT ON CONSTRAINT uq_reservations_platform_shop_wh_ref
            DO UPDATE
               SET trace_id   = EXCLUDED.trace_id,
                   updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "wh_id": wh_id,
            "ref": order_ref,
            "trace_id": trace_id,
        },
    )
    rid = int(row.scalar_one())

    # reservation_lines（幂等：qty>0, consumed_qty=0）
    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line, item_id,
                qty, consumed_qty, created_at, updated_at
            )
            VALUES (
                :rid, 1, :item_id,
                2, 0, now(), now()
            )
            ON CONFLICT ON CONSTRAINT ix_reservation_lines_res_refline
            DO UPDATE
               SET qty          = EXCLUDED.qty,
                   consumed_qty = EXCLUDED.consumed_qty,
                   updated_at   = now()
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    await session.commit()
    return trace_id


# ============================ 测试用例 ============================


async def test_order_lifecycle_v2_full_case(session: AsyncSession):
    trace_id = await _seed_full_lifecycle_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    keys = {s.key for s in stages if s.present}
    assert "created" in keys
    assert "reserved" in keys
    assert "reserved_consumed" in keys
    assert "outbound" in keys
    assert "shipped" in keys
    assert "returned" in keys

    assert summary.health in ("OK", "WARN")
    assert summary.health != "BAD"


async def test_order_lifecycle_v2_missing_shipped(session: AsyncSession):
    trace_id = await _seed_missing_shipped_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    keys = {s.key for s in stages if s.present}
    assert "reserved" in keys
    assert "shipped" not in keys

    assert summary.health in ("WARN", "BAD")
    joined = "\n".join(summary.issues)
    assert "发货" in joined or "ship" in joined.lower()


async def test_order_lifecycle_v2_reserve_only(session: AsyncSession):
    trace_id = await _seed_reserve_only_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    present_keys = {s.key for s in stages if s.present}

    assert "created" in present_keys
    assert "reserved" in present_keys

    assert "reserved_consumed" not in present_keys
    assert "outbound" not in present_keys
    assert "shipped" not in present_keys
    assert "returned" not in present_keys

    assert summary.health in ("WARN", "BAD")

    joined = "\n".join(summary.issues)
    assert (
        "预占已创建" in joined
        or "未检测到预占被消耗" in joined
        or "reservation_consumed" in joined
        or "预占已创建但未检测到消耗记录" in joined
    )
