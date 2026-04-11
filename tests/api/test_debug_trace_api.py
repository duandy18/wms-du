from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services._helpers import ensure_store
from tests.utils.ensure_minimal import ensure_item

from app.wms.stock.services.lots import ensure_lot_full

pytestmark = pytest.mark.asyncio


async def _seed_trace_case(session: AsyncSession) -> str:
    """
    构造一个最小 trace 场景（幂等版）：

    - trace_id = 'ORD-UT-1'
    - event_store: trace_id='ORD-UT-1', topic='ORDER.CREATED', key='ORD-UT-1'
    - orders: trace_id='ORD-UT-1'
    - order_fulfillment: actual_warehouse_id=1（执行仓事实）
    - outbound_commits_v2: trace_id='ORD-UT-1'
    - stock_ledger: trace_id='ORD-UT-1', reason='SHIPMENT', ref='ORD-UT-1', delta=-2

    Lot-World 终态注意：
    - stock_ledger 不再存在 batch_code 列；展示码来自 lots.lot_code（通过 lot_id JOIN）
    - 因此这里先 ensure SUPPLIER lot（lot_code='B-TRACE-1'）拿到 lot_id，再写 stock_ledger.lot_id
    """
    trace_id = "ORD-UT-1"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 3003
    order_ref = trace_id

    # items：满足 ledger FK（Phase M：items policy NOT NULL，必须最小合法插入）
    await ensure_item(
        session,
        id=int(item_id),
        sku=f"UT-SKU-{item_id}",
        name=f"UT-Item-{item_id}",
        expiry_required=True,
    )

    store_id = await ensure_store(
        session,
        platform=platform,
        shop_id=shop_id,
        name=f"UT-{platform}-{shop_id}",
    )

    # orders：最小订单头（只保证 trace 聚合能看到）
    row = await session.execute(
        text(
            """
            INSERT INTO orders (platform, shop_id, store_id, ext_order_no, status, trace_id, created_at, updated_at)
            VALUES (:p, :s, :store_id, :o, 'CREATED', :tid, now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  trace_id = EXCLUDED.trace_id,
                  updated_at = now()
            RETURNING id
            """
        ),
        {
            "p": platform,
            "s": shop_id,
            "store_id": int(store_id),
            "o": "UT-ORDER-TRACE-1",
            "tid": trace_id,
        },
    )
    order_id = int(row.scalar_one())

    # order_fulfillment：执行仓事实（orders 不再有 warehouse_id 列）
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
              :wid,
              :wid,
              'SERVICE_ASSIGNED',
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                   actual_warehouse_id  = EXCLUDED.actual_warehouse_id,
                   fulfillment_status   = EXCLUDED.fulfillment_status,
                   blocked_reasons      = NULL,
                   updated_at           = now()
            """
        ),
        {"oid": int(order_id), "wid": int(wh_id)},
    )

    # event_store
    await session.execute(
        text(
            """
            INSERT INTO event_store (trace_id, topic, key, payload, status, occurred_at)
            VALUES (:trace_id, 'ORDER.CREATED', :key, '{}'::jsonb, 'ok', now())
            """
        ),
        {"trace_id": trace_id, "key": order_ref},
    )

    # outbound_commits_v2
    # 单宇宙回归后：不再写 scope；唯一键为 (platform, shop_id, ref)
    # 测试环境可能不 TRUNCATE outbound_commits_v2，所以这里必须幂等。
    await session.execute(
        text(
            """
            INSERT INTO outbound_commits_v2 (platform, shop_id, ref, state, created_at, trace_id)
            VALUES (:p, :s, :ref, 'COMMITTED', now(), :tid)
            ON CONFLICT ON CONSTRAINT uq_outbound_commits_v2_platform_shop_ref DO NOTHING
            """
        ),
        {"p": platform, "s": shop_id, "ref": order_ref, "tid": trace_id},
    )

    # ensure SUPPLIER lot（展示码 lot_code='B-TRACE-1'）
    lot_code = "B-TRACE-1"
    prod = date.today()
    exp = prod + timedelta(days=365)
    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_code=str(lot_code),
        production_date=prod,
        expiry_date=exp,
    )

    # stock_ledger：SHIPMENT（lot_id 维度；不写 batch_code）
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
            VALUES (
                :trace_id,
                :wh_id,
                :item_id,
                :lot_id,
                'SHIPMENT',
                'SHIPMENT',
                :ref,
                1,
                -2,
                now(),
                now(),
                0,
                NULL,
                NULL
            )
            """
        ),
        {
            "trace_id": trace_id,
            "wh_id": wh_id,
            "item_id": item_id,
            "lot_id": int(lot_id),
            "ref": order_ref,
        },
    )

    await session.commit()
    return trace_id


async def test_debug_trace_basic(client, session: AsyncSession):
    """
    /debug/trace/{trace_id}

    验证：
      - 对于同一 trace_id，能够聚合 event_store / orders / outbound / ledger 记录；
      - summary/raw 中包含我们插入的关键字段。
    """
    trace_id = await _seed_trace_case(session)

    resp = await client.get(f"/debug/trace/{trace_id}")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["trace_id"] == trace_id
    events = data["events"]
    assert isinstance(events, list) and len(events) >= 3

    sources = {e["source"] for e in events}
    assert "ledger" in sources
    assert "outbound" in sources
    assert ("event_store" in sources) or ("order" in sources)

    # 校验 ORDER.CREATED（如果 event_store 存在）
    if "event_store" in sources:
        assert any(
            e["source"] == "event_store" and e["kind"] == "ORDER.CREATED" and e.get("ref") == "ORD-UT-1" for e in events
        )

    # 校验 SHIPMENT ledger
    assert any(e["source"] == "ledger" and e["kind"] == "SHIPMENT" and e["raw"].get("delta") == -2 for e in events)
