# tests/services/test_outbound_ledger_consistency.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.outbound import OutboundLine
from app.services.outbound_service import OutboundService

UTC = timezone.utc

pytestmark = pytest.mark.asyncio


async def _seed_minimal_order_for_outbound(
    session: AsyncSession,
) -> tuple[int, str, int, int, str]:
    """
    为出库写台账准备一条最小订单头：

    - platform = 'PDD'
    - shop_id = 'UT-SHOP'
    - warehouse_id = 1  （conftest 已种好 WH-1）
    - item_id = 1      （conftest 已种好 ITEM-1，batch='NEAR' 有库存）
    - ext_order_no = 'LEDGER-OUT-1'
    - ref = ORD:{platform}:{shop_id}:{ext_order_no}
    """
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 1
    ext_order_no = "LEDGER-OUT-1"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"
    trace_id = "TRACE-LEDGER-OUT-1"

    # 确保 item 存在（conftest 已经种了 id=1，这里幂等兜一层）
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
            "sku": "SKU-0001",
            "name": "UT-ITEM-1",
        },
    )

    # 插入一条订单头
    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                warehouse_id,
                status,
                trace_id,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :ext_order_no,
                :wh_id,
                'CREATED',
                :trace_id,
                now(),
                now()
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

    await session.commit()
    return order_id, order_ref, wh_id, item_id, trace_id


@pytest.mark.asyncio
async def test_outbound_commit_writes_consistent_ledger(session: AsyncSession) -> None:
    """
    验证：出库 commit 之后，台账中的 SHIPMENT 记录在维度上与 stocks 槽位一致。

    这里不关心业务流程细节（reserve / audit / trace 等），只关心：

    - OutboundService.commit 能在当前 HEAD schema 下正常运行；
    - 写出来的 stock_ledger 行：
        * reason = 'SHIPMENT'
        * warehouse_id / item_id / batch_code维度正确
        * delta < 0（出库）
    """
    order_id, order_ref, wh_id, item_id, trace_id = await _seed_minimal_order_for_outbound(
        session
    )

    # 使用 conftest 的种子：stocks(warehouse_id=1, item_id=1, batch_code='NEAR', qty=10)
    batch_code = "NEAR"
    qty_to_ship = 3

    svc = OutboundService()
    lines = [
        OutboundLine(
            item_id=item_id,
            batch_code=batch_code,
            qty=qty_to_ship,
            warehouse_id=wh_id,
        )
    ]

    occurred_at = datetime.now(UTC)

    # 不抛异常即可；返回结果结构因版本演进可能变化，不在此强约束
    result = await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )
    assert isinstance(result, dict)

    # 查找 SHIPMENT 台账记录（按 ref + reason）
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    warehouse_id,
                    item_id,
                    batch_code,
                    reason,
                    ref,
                    delta,
                    after_qty
                  FROM stock_ledger
                 WHERE reason = 'SHIPMENT'
                   AND ref = :ref
                 ORDER BY occurred_at, id
                """
            ),
            {"ref": order_ref},
        )
    ).mappings().all()

    assert rows, "expected at least one SHIPMENT ledger row for outbound commit"

    for r in rows:
        assert int(r["warehouse_id"]) == wh_id
        assert int(r["item_id"]) == item_id
        assert r["batch_code"] == batch_code
        assert r["reason"] == "SHIPMENT"
        assert int(r["delta"]) < 0  # 出库必须是负数
