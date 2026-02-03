# tests/services/order_lifecycle_v2/seeders.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_full_lifecycle_case(session: AsyncSession) -> str:
    """
    构造一个“正常履约 + 退货”的生命周期场景（不依赖任何旧预占相关表）：

    - trace_id = 'LIFE-UT-1'
    - orders: 一条
    - outbound_commits_v2: 一条 COMMITTED（如已有记录则跳过）
    - audit_events: 一条 flow=OUTBOUND（兜底）
    - stock_ledger:
        * SHIPMENT delta=-2
        * RETURN_IN delta=+1
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
        {"item_id": item_id, "sku": f"UT-SKU-{item_id}", "name": f"UT-Item-{item_id}"},
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

    # outbound_commits_v2
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
        {"platform": platform, "shop_id": shop_id, "ref": order_ref, "trace_id": trace_id},
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

    # stock_ledger：SHIPMENT / RETURN_IN
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
        {"trace_id": trace_id, "wh_id": wh_id, "item_id": item_id, "ref": order_ref},
    )

    await session.commit()
    return trace_id


async def seed_missing_shipped_case(session: AsyncSession) -> str:
    """
    构造一个“有 outbound，但没有 shipped”的生命周期场景（不依赖旧预占相关表）：
    """
    trace_id = "LIFE-UT-2"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4002
    ext_order_no = "UT-ORDER-2"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"item_id": item_id, "sku": f"UT-SKU-{item_id}", "name": f"UT-Item-{item_id}"},
    )

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
        {"platform": platform, "shop_id": shop_id, "ref": order_ref, "trace_id": trace_id},
    )

    await session.commit()
    return trace_id


async def seed_created_only_case(session: AsyncSession) -> str:
    """
    构造一个“只有 created，没有 outbound/shipped/returned”的生命周期场景（不依赖旧预占相关表）：
    """
    trace_id = "LIFE-UT-3"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4003
    ext_order_no = "UT-ORDER-3"

    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"item_id": item_id, "sku": f"UT-SKU-{item_id}", "name": f"UT-Item-{item_id}"},
    )

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

    await session.commit()
    return trace_id
