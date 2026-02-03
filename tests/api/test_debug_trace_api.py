# tests/api/test_debug_trace_api.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_trace_case(session: AsyncSession) -> str:
    """
    构造一个最小 trace 场景（幂等版）：

    - trace_id = 'ORD-UT-1'
    - event_store: trace_id='ORD-UT-1', topic='ORDER.CREATED', key='ORD-UT-1'
    - orders: trace_id='ORD-UT-1'
    - outbound_commits_v2: trace_id='ORD-UT-1'
    - stock_ledger: trace_id='ORD-UT-1', reason='SHIPMENT', ref='ORD-UT-1', delta=-2
    """
    trace_id = "ORD-UT-1"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 3003
    order_ref = trace_id

    # items：满足 ledger FK
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

    # orders：最小订单行（只保证 trace 聚合能看到）
    await session.execute(
        text(
            """
            INSERT INTO orders (platform, shop_id, ext_order_no, warehouse_id, status, trace_id, created_at, updated_at)
            VALUES (:p, :s, :o, :w, 'CREATED', :tid, now(), now())
            ON CONFLICT DO NOTHING
            """
        ),
        {"p": platform, "s": shop_id, "o": "UT-ORDER-TRACE-1", "w": wh_id, "tid": trace_id},
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
    await session.execute(
        text(
            """
            INSERT INTO outbound_commits_v2 (platform, shop_id, ref, state, created_at, trace_id)
            VALUES (:p, :s, :ref, 'COMMITTED', now(), :tid)
            ON CONFLICT (platform, shop_id, ref) DO NOTHING
            """
        ),
        {"p": platform, "s": shop_id, "ref": order_ref, "tid": trace_id},
    )

    # stock_ledger：SHIPMENT
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
            VALUES (
                :trace_id,
                :wh_id,
                :item_id,
                'B-TRACE-1',
                'SHIPMENT',
                :ref,
                1,
                -2,
                now(),
                now(),
                0
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
            e["source"] == "event_store"
            and e["kind"] == "ORDER.CREATED"
            and e.get("ref") == "ORD-UT-1"
            for e in events
        )

    # 校验 SHIPMENT ledger
    assert any(
        e["source"] == "ledger" and e["kind"] == "SHIPMENT" and e["raw"].get("delta") == -2
        for e in events
    )
