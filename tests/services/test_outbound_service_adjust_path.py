from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services._helpers import ensure_store

from app.wms.outbound.services.outbound_commit_service import OutboundService
from app.wms.stock.services.lots import ensure_lot_full

UTC = timezone.utc


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
        text(
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


async def _ensure_seed_stock_slot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> tuple[int, int, str, int]:
    """
    为出库测试提供稳定的库存槽位（Lot-World 终态）：

    - 使用 ensure_lot_full 创建/复用 SUPPLIER lot（identity = lot_code_key）
    - upsert stocks_lot(item_id, warehouse_id, lot_id) qty

    返回：(item_id, warehouse_id, batch_code, qty_sum)
    """
    wh = int(warehouse_id)
    it = int(item_id)
    code_raw = str(batch_code).strip()
    assert code_raw, "batch_code must be non-empty for supplier lot"
    qty_i = int(qty)
    assert qty_i > 0, "seed qty must be positive"

    # 保证该商品走 REQUIRED（批次受控），避免执行域把 batch_code 清空导致走 INTERNAL
    await session.execute(
        text("UPDATE items SET expiry_policy='REQUIRED'::expiry_policy WHERE id=:i"),
        {"i": it},
    )

    # ✅ 终态：supplier lot 必须走 ensure_lot_full（内部会写 lot_code_key，并匹配 partial unique index）
    lot_id = await ensure_lot_full(
        session,
        item_id=it,
        warehouse_id=wh,
        lot_code=code_raw,
        production_date=None,
        expiry_date=None,
    )

    # ✅ upsert stocks_lot 余额（保证后续扣减一定命中）
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
            VALUES (:item_id, :wid, :lot_id, :qty)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": it, "wid": wh, "lot_id": int(lot_id), "qty": qty_i},
    )

    await session.flush()
    return it, wh, code_raw, qty_i


async def _pick_one_stock_slot(session: AsyncSession):
    """
    旧版本是从 baseline 里“随机挑一个 qty>0 的 lot_code 槽位”，在终态合同下会引发偶发缺货/漂移。

    现在改为：显式 seed 一个稳定槽位，确保 OutboundService.commit 必然命中同一 lot_id。
    """
    return await _ensure_seed_stock_slot(
        session,
        item_id=3001,
        warehouse_id=1,
        batch_code="B-CONC-1",
        qty=20,
    )


@pytest.mark.asyncio
async def test_outbound_commit_merges_lines_and_writes_ledger(session: AsyncSession):
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 5:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试总扣减为 5")

    order_id = "UT:PH3:OUT-TEST-1"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    lines = [
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 2},
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 3},
    ]

    svc = OutboundService()
    ts = datetime.now(timezone.utc)

    result = await svc.commit(
        session,
        order_id=order_id,
        lines=lines,
        occurred_at=ts,
    )

    assert result["status"] == "OK"
    assert result["committed_lines"] == 1
    assert result["total_qty"] == 5

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta = int(row.scalar() or 0)
    assert total_delta == -5


@pytest.mark.asyncio
async def test_outbound_commit_idempotent_same_payload(session: AsyncSession):
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 3:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试")

    order_id = "UT:PH3:OUT-TEST-2"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    lines = [
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 3},
    ]

    svc = OutboundService()
    ts = datetime.now(timezone.utc)

    r1 = await svc.commit(session, order_id=order_id, lines=lines, occurred_at=ts)
    assert r1["status"] == "OK"

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta_1 = int(row.scalar() or 0)
    assert total_delta_1 == -3

    r2 = await svc.commit(session, order_id=order_id, lines=lines, occurred_at=ts)
    assert r2["status"] == "OK"
    assert r2["total_qty"] <= 0

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta_2 = int(row.scalar() or 0)
    assert total_delta_2 == total_delta_1
