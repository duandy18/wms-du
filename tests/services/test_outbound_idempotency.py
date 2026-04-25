# tests/services/test_outbound_idempotency.py
"""
基于 Phase 3 出库实现（OutboundService）的幂等性测试：
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.outbound.services.outbound_commit_service import OutboundService
from tests.services._helpers import ensure_store
from tests.utils.ensure_minimal import ensure_item, set_stock_qty

UTC = timezone.utc


async def _ensure_item_row(
    session: AsyncSession,
    *,
    item_id: int,
) -> None:
    row = await session.execute(
        sa.text("SELECT 1 FROM items WHERE id = :id LIMIT 1"),
        {"id": item_id},
    )
    if row.first() is None:
        sku = f"IDEM-SKU-{item_id}"
        name = f"IDEM-ITEM-{item_id}"
        await ensure_item(session, id=int(item_id), sku=sku, name=name)

    # 关键：本测试要走 batch_code 语义，必须 REQUIRED
    await session.execute(
        text("UPDATE items SET expiry_policy='REQUIRED'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
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
    await _ensure_item_row(session, item_id=item_id)

    await set_stock_qty(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code=str(batch_code),
        qty=int(qty),
    )
    await session.commit()


async def _ensure_order_ref_exists(session: AsyncSession, *, order_ref: str) -> None:
    parts = str(order_ref).split(":", 2)
    assert len(parts) == 3, f"invalid test order_ref: {order_ref}"
    platform, shop_id, ext_order_no = parts
    store_id = await ensure_store(
        session,
        platform=str(platform).upper(),
        shop_id=str(shop_id),
        name=f"UT-{str(platform).upper()}-{shop_id}",
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO orders(platform, shop_id, store_id, ext_order_no, status, created_at, updated_at)
            VALUES (:p, :sid, :store_id, :ext, 'CREATED', now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "p": str(platform).upper(),
            "sid": str(shop_id),
            "store_id": int(store_id),
            "ext": str(ext_order_no),
        },
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
    row = await session.execute(
        sa.text(
            """
            SELECT COALESCE(SUM(l.delta), 0) AS s
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.warehouse_id = :wid
               AND l.item_id      = :item
               AND lo.lot_code    = :code
               AND l.ref          = :ref
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
    warehouse_id = 1
    item_id = 7651
    batch_code = "B-IDEM-1"

    await _seed_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        qty=100,
    )

    order_id = f"PDD:CUST001:SO-IDEM-{int(datetime.now(UTC).timestamp())}"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    before_delta = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert before_delta == 0

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

    delta_after_first = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert delta_after_first == -8

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
    assert r2_line["status"] == "OK"
    assert r2_line.get("idempotent") is True

    delta_after_second = await _sum_ledger_for_ref(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        order_id=order_id,
    )
    assert delta_after_second == -8
