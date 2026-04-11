from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lots import ensure_lot_full
from tests.utils.ensure_minimal import ensure_item
from tests.services._helpers import ensure_store


async def _upsert_order_and_fulfillment(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    trace_id: str,
    wh_id: int,
    status: str = "CREATED",
    fulfillment_status: str = "SERVICE_ASSIGNED",
) -> int:
    """
    Phase 5+ 事实边界：
    - orders：只承载订单头（不再有 warehouse_id）
    - order_fulfillment：承载执行仓/履约快照（这里写 actual_warehouse_id）
    """
    store_id = await ensure_store(
        session,
        platform=platform,
        shop_id=shop_id,
        name=f"UT-{platform}-{shop_id}",
    )

    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                store_id,
                ext_order_no,
                status,
                trace_id,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :store_id,
                :ext_order_no,
                :status,
                :trace_id,
                now(),
                now()
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  status = EXCLUDED.status,
                  trace_id = COALESCE(EXCLUDED.trace_id, orders.trace_id),
                  updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "store_id": int(store_id),
            "ext_order_no": ext_order_no,
            "status": status,
            "trace_id": trace_id,
        },
    )
    order_id = int(row.scalar_one())
    assert order_id > 0

    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
              order_id,
              planned_warehouse_id,
              actual_warehouse_id,
              fulfillment_status,
              blocked_reasons,
              updated_at
            )
            VALUES (
              :oid,
              NULL,
              :awid,
              :fs,
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = now()
            """
        ),
        {"oid": int(order_id), "awid": int(wh_id), "fs": str(fulfillment_status)},
    )

    return int(order_id)


async def seed_full_lifecycle_case(session: AsyncSession) -> str:
    """
    构造一个“正常履约 + 退货”的生命周期场景（不依赖任何旧预占相关表）：

    - trace_id = 'LIFE-UT-1'
    - orders: 一条（Phase5+：不含 warehouse_id）
    - order_fulfillment: 一条（写 actual_warehouse_id）
    - outbound_commits_v2: 一条 COMMITTED（如已有记录则跳过）
    - audit_events: 一条 flow=OUTBOUND（兜底）
    - stock_ledger:
        * SHIPMENT delta=-2
        * RETURN_IN delta=+1

    Lot-World 终态注意：
    - stock_ledger 展示码应来自 lots.lot_code（通过 lot_id JOIN）
    - 这里先 ensure SUPPLIER lot（lot_code='B-LIFE-1'）拿到 lot_id，再写 stock_ledger.lot_id

    ✅ 终态收口：禁止 tests 直接 INSERT INTO lots
    -> 统一走 app/services/stock/lots.py: ensure_lot_full
    """
    trace_id = "LIFE-UT-1"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 4001
    ext_order_no = "UT-ORDER-1"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    # 确保 warehouse 存在（避免依赖 baseline 漂移）
    await session.execute(
        text("INSERT INTO warehouses (id, name) VALUES (:w, 'WH-UT') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh_id)},
    )

    # items（本场景显式走 SUPPLIER lot，因此商品必须站到 REQUIRED）
    await ensure_item(
        session,
        id=int(item_id),
        sku=f"UT-SKU-{item_id}",
        name=f"UT-Item-{item_id}",
        expiry_required=True,
    )

    # orders + order_fulfillment（Phase5+）
    await _upsert_order_and_fulfillment(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        trace_id=trace_id,
        wh_id=wh_id,
        status="CREATED",
        fulfillment_status="SERVICE_ASSIGNED",
    )

    # outbound_commits_v2
    # 单宇宙回归后：唯一键为 (platform, shop_id, ref)
    # 测试环境可能不 TRUNCATE outbound_commits_v2，所以这里必须幂等。
    await session.execute(
        text(
            """
            INSERT INTO outbound_commits_v2 (
                platform, shop_id, ref, state, created_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :ref, 'COMMITTED', now(), :trace_id
            )
            ON CONFLICT ON CONSTRAINT uq_outbound_commits_v2_platform_shop_ref DO NOTHING
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

    # ensure SUPPLIER lot (lot_code 展示码)
    lot_code = "B-LIFE-1"
    prod = date(2030, 1, 1)
    exp = prod + timedelta(days=365)
    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_code=str(lot_code),
        production_date=prod,
        expiry_date=exp,
    )

    # stock_ledger：SHIPMENT / RETURN_IN（lot_id 维度；不写 batch_code）
    await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
                trace_id,
                warehouse_id,
                item_id,
                lot_id,
                reason,
                reason_canon,
                ref,
                ref_line,
                delta,
                occurred_at,
                created_at,
                after_qty,
                production_date,
                expiry_date
            )
            VALUES
            (
                :trace_id,
                :wh_id,
                :item_id,
                :lot_id,
                'SHIPMENT',
                'SHIPMENT',
                :ref,
                1,
                -2,
                now() + INTERVAL '5 min',
                now() + INTERVAL '5 min',
                0,
                NULL,
                NULL
            ),
            (
                :trace_id,
                :wh_id,
                :item_id,
                :lot_id,
                'RETURN_IN',
                'RECEIPT',
                :ref,
                1,
                1,
                now() + INTERVAL '20 min',
                now() + INTERVAL '20 min',
                1,
                :prod,
                :exp
            )
            """
        ),
        {
            "trace_id": trace_id,
            "wh_id": wh_id,
            "item_id": item_id,
            "lot_id": int(lot_id),
            "ref": order_ref,
            "prod": prod,
            "exp": exp,
        },
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
        text("INSERT INTO warehouses (id, name) VALUES (:w, 'WH-UT') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh_id)},
    )

    await ensure_item(session, id=int(item_id), sku=f"UT-SKU-{item_id}", name=f"UT-Item-{item_id}")

    # orders + order_fulfillment（Phase5+）
    await _upsert_order_and_fulfillment(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        trace_id=trace_id,
        wh_id=wh_id,
        status="CREATED",
        fulfillment_status="SERVICE_ASSIGNED",
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
            ON CONFLICT ON CONSTRAINT uq_outbound_commits_v2_platform_shop_ref DO NOTHING
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
        text("INSERT INTO warehouses (id, name) VALUES (:w, 'WH-UT') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh_id)},
    )

    await ensure_item(session, id=int(item_id), sku=f"UT-SKU-{item_id}", name=f"UT-Item-{item_id}")

    # orders + order_fulfillment（Phase5+）
    await _upsert_order_and_fulfillment(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        trace_id=trace_id,
        wh_id=wh_id,
        status="CREATED",
        fulfillment_status="SERVICE_ASSIGNED",
    )

    await session.commit()
    return trace_id
