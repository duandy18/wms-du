# tests/api/test_order_lifecycle_v2.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService

pytestmark = pytest.mark.asyncio


async def _seed_lifecycle_case(session: AsyncSession) -> str:
    """
    构造一个覆盖核心生命周期节点的最小场景：

    - 使用 OrderService.ingest 落一条订单（带 trace_id），提供 created 节点；
    - 插入 reservations + reservation_lines（consumed_qty > 0），提供
      reserved / reserved_consumed 节点；
    - 插入两条 stock_ledger 记录：
        * RESERVE  delta=-2
        * SHIPMENT delta=-2
      提供负向出库 + 明确 SHIP 记账，用于 shipped 节点。
    """

    trace_id = "TRACE-LIFECYCLE-1"
    platform = "PDD"
    shop_id = "LC-SHOP"
    ext_order_no = "ORD-LIFECYCLE-1"
    wh_id = 1
    item_id = 4001

    now = datetime.now(timezone.utc)

    # 1) 通过服务层落订单，确保 orders.trace_id 正确写入
    await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        order_amount=100,
        pay_amount=100,
        items=[
            {"item_id": item_id, "qty": 2},
        ],
        address=None,
        extras=None,
        trace_id=trace_id,
    )

    # 查询刚刚插入的订单 id（用于 RMA/source_id 等关联）
    row = await session.execute(
        text(
            """
            SELECT id
              FROM orders
             WHERE platform = :platform
               AND shop_id  = :shop_id
               AND ext_order_no = :ext
               AND trace_id = :trace_id
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ext": ext_order_no,
            "trace_id": trace_id,
        },
    )
    order_id = int(row.scalar_one())

    # 2) 准备 items 表基础数据（避免 FK / NOT NULL 报错）
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
            "sku": f"LC-SKU-{item_id}",
            "name": f"LC-Item-{item_id}",
        },
    )

    # 3) reservations（头）—— 统一 trace_id
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
            # 这里 ref 用 ext_order_no 或统一 order_ref 均可，
            # 对生命周期 v2 来说关键是 trace_id。
            "ref": ext_order_no,
            "trace_id": trace_id,
        },
    )
    rid = int(row.scalar_one())

    # 4) reservation_lines —— consumed_qty > 0，用于生成 reservation_consumed 事件
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
                2,
                now(),
                now()
            )
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    # 5) stock_ledger：一条 RESERVE + 一条 SHIPMENT（均为负向出库）
    #
    #  - RESERVE  : 提供“预占产生”的 ledger 证据
    #  - SHIPMENT : 提供“发货记账”的明确 evidence（reason 含 SHIP）
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
                'LC-BATCH-1',
                'RESERVE',
                :ref,
                1,
                -2,
                now(),
                now(),
                100
            )
            """
        ),
        {
            "trace_id": trace_id,
            "wh_id": wh_id,
            "item_id": item_id,
            "ref": ext_order_no,
        },
    )

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
                'LC-BATCH-1',
                'SHIPMENT',
                :ref,
                1,
                -2,
                now() + INTERVAL '5 minutes',
                now() + INTERVAL '5 minutes',
                98
            )
            """
        ),
        {
            "trace_id": trace_id,
            "wh_id": wh_id,
            "item_id": item_id,
            "ref": ext_order_no,
        },
    )

    await session.commit()
    return trace_id


async def test_order_lifecycle_v2_basic(
    client: AsyncClient,
    session: AsyncSession,
):
    """
    /diagnostics/lifecycle/order-v2

    验证：
      - 对于同一 trace_id，生命周期 v2 能识别核心阶段：
        created / reserved / reserved_consumed / shipped；
      - summary.health 至少为 OK / WARN，不应是 BAD；
      - 各阶段 present 标记符合我们构造的数据。
    """
    trace_id = await _seed_lifecycle_case(session)

    resp = await client.get(
        "/diagnostics/lifecycle/order-v2",
        params={"trace_id": trace_id},
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["ok"] is True
    assert data["trace_id"] == trace_id

    stages = data["stages"]
    summary = data["summary"]

    # 根据 key 聚合 stage
    stages_by_key = {st["key"]: st for st in stages}

    # 关键节点必须存在
    for key in ["created", "reserved", "reserved_consumed", "shipped"]:
        assert key in stages_by_key, f"missing lifecycle stage: {key}"
        assert stages_by_key[key]["present"] is True, f"stage {key} should be present"

    # outbound / returned 这里不强制要求 present，后续可以通过扩展 seed 场景来覆盖
    assert summary["health"] in ("OK", "WARN")
    assert isinstance(summary.get("issues"), list)
