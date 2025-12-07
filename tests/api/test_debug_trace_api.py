# tests/api/test_debug_trace_api.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_trace_case(session: AsyncSession) -> str:
    """
    构造一个最小 trace 场景：

    - trace_id = 'ORD-UT-1'
    - event_store: trace_id='ORD-UT-1', topic='ORDER.CREATED', key='ORD-UT-1'
    - reservations: platform=PDD, shop=UT-SHOP, wh=1, ref='ORD-UT-1', trace_id='ORD-UT-1'
    - reservation_lines: item 3003 qty=2
    - stock_ledger: trace_id='ORD-UT-1', reason='RESERVE', ref='ORD-UT-1', delta=-2

    所有记录使用同一个字符串 'ORD-UT-1' 作为 trace key：
      - event_store.trace_id     = 'ORD-UT-1'
      - stock_ledger.trace_id    = 'ORD-UT-1'
      - reservations.trace_id    = 'ORD-UT-1'
      - reservations.ref         = 'ORD-UT-1'（兼容历史 ref 口径）
    """
    trace_id = "ORD-UT-1"
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 3003
    order_ref = trace_id

    # event_store: trace_id + payload + occurred_at
    await session.execute(
        text(
            """
            INSERT INTO event_store (trace_id, topic, key, payload, status, occurred_at)
            VALUES (:trace_id, 'ORDER.CREATED', :key, '{}'::jsonb, 'ok', now())
            """
        ),
        {"trace_id": trace_id, "key": order_ref},
    )

    # reservation 头：现在以 trace_id 为主，ref 为退路
    row = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform,
                shop_id,
                warehouse_id,
                ref,
                status,
                created_at,
                updated_at,
                expire_at,
                trace_id
            )
            VALUES (
                :platform,
                :shop_id,
                :wh_id,
                :ref,
                'open',
                now(),
                now(),
                now() + INTERVAL '1 hour',
                :trace_id
            )
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

    # reservation line
    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id,
                ref_line,
                item_id,
                qty,
                consumed_qty,
                created_at,
                updated_at
            )
            VALUES (
                :rid,
                1,
                :item_id,
                2,
                0,
                now(),
                now()
            )
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    # items：满足 stock_ledger 的 FK + NOT NULL 约束
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

    # stock_ledger：trace_id + reason + delta
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
                'RESERVE',
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
      - 对于同一 trace_id，能够聚合 reservations / reservation_lines / ledger 记录；
      - 如果 event_store 中有记录，也能被串入轨迹；
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
    # 至少包含 reservation / ledger；event_store 如存在则一并校验
    assert "reservation" in sources
    assert "ledger" in sources

    # 如果有 event_store 事件，则验证 ORDER.CREATED 内容
    if "event_store" in sources:
        assert any(
            e["source"] == "event_store"
            and e["kind"] == "ORDER.CREATED"
            and e.get("ref") == "ORD-UT-1"
            for e in events
        )

    # 确认有一条 reservation 事件，其 raw.ref == 'ORD-UT-1'
    assert any(e["source"] == "reservation" and e["raw"].get("ref") == "ORD-UT-1" for e in events)

    # 确认有一条 RESERVE ledger delta=-2
    assert any(
        e["source"] == "ledger" and e["kind"] == "RESERVE" and e["raw"].get("delta") == -2
        for e in events
    )
