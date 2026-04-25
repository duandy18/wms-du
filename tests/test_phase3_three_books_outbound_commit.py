# tests/test_phase3_three_books_outbound_commit.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.outbound.services.outbound_commit_service import OutboundService
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.wms.shared.services.three_books_consistency import verify_commit_three_books
from tests.services._helpers import ensure_store
from tests.utils.ensure_minimal import set_stock_qty


async def _pick_item_for_stock_in(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM items
                 ORDER BY id ASC
                 LIMIT 1
                """
            )
        )
    ).first()
    if not row:
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Phase 3 出库合同测试")
    return int(row[0])


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


async def _load_ledger_lot_id(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    ref: str,
    ref_line: int = 1,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT lot_id
                  FROM stock_ledger
                 WHERE warehouse_id = :warehouse_id
                   AND item_id = :item_id
                   AND ref = :ref
                   AND ref_line = :ref_line
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "ref": str(ref),
                "ref_line": int(ref_line),
            },
        )
    ).first()

    if not row or row[0] is None:
        raise AssertionError(
            {
                "msg": "outbound commit ledger row must carry lot_id",
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "ref": str(ref),
                "ref_line": int(ref_line),
            }
        )

    return int(row[0])


@pytest.mark.asyncio
async def test_phase3_outbound_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（出库链路）：
    - 先用 lot-only 测试 helper 造库存（写 ledger + stocks_lot）
    - 再用 OutboundService.commit 出库（写 ledger + stocks_lot + snapshot 尾门）
    - 最后用三账校验器兜底复验：ledger(ref/ref_line) + stocks_lot + snapshot(today) 一致
    """
    utc = timezone.utc
    now = datetime.now(utc)

    outbound_svc = OutboundService()

    warehouse_id = 1
    item_id = await _pick_item_for_stock_in(session)
    batch_code = "B-PH3-OUT"

    # 入库造数：给足库存，避免出库不足。测试造数统一走 lot-only helper，不再调用 StockService.adjust。
    await set_stock_qty(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        qty=10,
    )

    # 出库：扣 3
    order_id = "UT:PH3:OUT"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    ship_qty = 3

    res = await outbound_svc.commit(
        session=session,
        order_id=order_id,
        lines=[
            {
                "item_id": item_id,
                "warehouse_id": warehouse_id,
                "batch_code": batch_code,
                "qty": ship_qty,
            }
        ],
        occurred_at=now,
        trace_id="PH3-UT-TRACE-OUT",
    )

    assert res["status"] == "OK"

    lot_id = await _load_ledger_lot_id(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        ref=str(order_id),
        ref_line=1,
    )

    # 双保险：再跑一次快照 + 三账校验（只对本次 touched key）
    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=str(order_id),
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "lot_id": lot_id,
                "lot_code": batch_code,
                "qty": -ship_qty,  # 出库 delta 为负
                "ref": str(order_id),
                "ref_line": 1,
            }
        ],
        at=now,
    )
