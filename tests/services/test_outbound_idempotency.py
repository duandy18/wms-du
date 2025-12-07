# tests/services/test_outbound_idempotency.py
"""
基于 Phase 3 出库实现（OutboundService）的幂等性测试：

- 出库入口：OutboundService.commit(session, order_id=..., lines=[...])
- 粒度： (warehouse_id, item_id, batch_code)
- 幂等键： order_id（本测试用 "PLATFORM:SHOP_ID:REF" 字符串模拟）
- 规则：
    * 第一次调用：扣减目标数量（例如 8），写一条负 delta 到 stock_ledger；
    * 第二次用同一个 order_id + 同样的 lines 调用：不再扣减，total_qty=0，ledger 中仍然只有 -8。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService
from app.services.stock_service import StockService

UTC = timezone.utc


async def _ensure_item_row(
    session: AsyncSession,
    *,
    item_id: int,
) -> None:
    """
    直接用 SQL 确保 items 表中存在给定 item_id 的记录。

    - 不依赖 ORM Item 构造（避免 uom 等 property 限制）；
    - 仅插入主键 id + sku + name + enabled，其他列走默认值/可空。

    假设 items 表至少包含：
        id (PK), sku, name, enabled
    """
    # 先查一遍，避免重复 insert
    row = await session.execute(
        sa.text("SELECT 1 FROM items WHERE id = :id LIMIT 1"),
        {"id": item_id},
    )
    if row.first() is not None:
        return

    sku = f"IDEM-SKU-{item_id}"
    name = f"IDEM-ITEM-{item_id}"

    # 显式插入最小字段集合；ON CONFLICT 保证重复调用安全
    await session.execute(
        sa.text(
            """
            INSERT INTO items (id, sku, name, enabled)
            VALUES (:id, :sku, :name, TRUE)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": item_id, "sku": sku, "name": name},
    )
    await session.commit()


async def _seed_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    qty: int,
) -> None:
    """
    使用 StockService.adjust 为指定 (warehouse_id, item_id, batch_code) 预先加库存。

    步骤：
    1) 确保 items 表中存在该 item_id；
    2) 调用 StockService.adjust 做一次入库。

    约束对齐 StockService.adjust：
    - 入库 delta>0 时，必须提供 batch_code；
    - production_date / expiry_date 至少其一非空。
    这里使用今天作为生产日期。
    """
    await _ensure_item_row(session, item_id=item_id)

    svc = StockService()
    ts = datetime.now(UTC)

    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=qty,
        reason="INBOUND_SEED",
        ref="SEED-STOCK-IDEM",
        ref_line=1,
        occurred_at=ts,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        production_date=date.today(),
        expiry_date=None,
    )
    await session.commit()


async def _sum_ledger_for_ref(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    order_id: str,
) -> int:
    """
    查询 stock_ledger 中特定 (warehouse_id, item_id, batch_code, ref=order_id) 的 delta 总和。
    """
    row = await session.execute(
        sa.text(
            """
            SELECT COALESCE(SUM(delta), 0) AS s
              FROM stock_ledger
             WHERE warehouse_id = :wid
               AND item_id      = :item
               AND batch_code   = :code
               AND ref          = :ref
            """
        ),
        {
            "wid": warehouse_id,
            "item": item_id,
            "code": batch_code,
            "ref": order_id,
        },
    )
    return int(row.scalar() or 0)


@pytest.mark.asyncio
async def test_outbound_idempotent_commit(session: AsyncSession):
    """
    验证 OutboundService.commit 的幂等性：

    场景：
    - 预先向 (wh=1, item=7651, batch=B-IDEM-1) 加 100 库存；
    - 第一次 commit：扣 8，ledger 累计 -8；
    - 第二次 commit（同一个 order_id + 相同 lines）：不再扣减，total_qty=0，ledger 仍然是 -8。
    """
    warehouse_id = 1
    item_id = 7651
    batch_code = "B-IDEM-1"

    # 1) 预先加库存
    await _seed_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        qty=100,
    )

    # 2) 调用前 ledger 初始值应为 0
    order_id = f"PDD:CUST001:SO-IDEM-{int(datetime.now(UTC).timestamp())}"
    before_delta = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert before_delta == 0

    # 3) 准备出库行：扣减 8
    lines = [
        {
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "batch_code": batch_code,
            "qty": 8,
        }
    ]
    occurred_at = datetime.now(UTC)
    trace_id = f"trace:idem:{occurred_at.isoformat(timespec='seconds')}"

    svc = OutboundService()

    # 4) 第一次出库：应实际扣 8
    res1 = await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )

    assert res1["status"] == "OK"
    assert res1["total_qty"] == 8
    assert res1["committed_lines"] == 1
    assert len(res1["results"]) == 1
    r1_line = res1["results"][0]
    assert r1_line["item_id"] == item_id
    assert r1_line["warehouse_id"] == warehouse_id
    assert r1_line["batch_code"] == batch_code
    assert r1_line["qty"] == 8
    assert r1_line["status"] == "OK"

    # ledger 中应累计 -8
    delta_after_first = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert delta_after_first == -8

    # 5) 第二次出库（同一个 order_id，同样的 lines）：
    #    OutboundService 应判定“已扣满”，不再扣减 → total_qty=0
    res2 = await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )

    assert res2["status"] == "OK"
    assert res2["total_qty"] == 0
    assert res2["committed_lines"] == 0
    assert len(res2["results"]) == 1
    r2_line = res2["results"][0]
    assert r2_line["item_id"] == item_id
    assert r2_line["warehouse_id"] == warehouse_id
    assert r2_line["batch_code"] == batch_code
    # 第二次调用视为幂等重复：不再扣减，但返回 OK + idempotent=True
    assert r2_line["status"] == "OK"
    assert r2_line.get("idempotent") is True

    # ledger 中仍然只是一笔 -8，没有重复扣
    delta_after_second = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert delta_after_second == -8
