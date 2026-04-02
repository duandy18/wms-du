# tests/test_phase3_three_books_outbound_commit.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service_impl import OutboundService
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.services.stock_service import StockService
from app.services.three_books_consistency import verify_receive_commit_three_books
from tests.services._helpers import ensure_store


async def _pick_item_for_stock_in(session: AsyncSession) -> tuple[int, bool]:
    """
    尽量挑 expiry_policy=NONE 的 item，避免入库日期推导依赖 shelf_life 参数。
    若找不到，就退回任意 item，并在入库时显式填 expiry_date。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM items
                 WHERE COALESCE(expiry_policy::text, 'NONE') <> 'REQUIRED'
                 ORDER BY id ASC
                 LIMIT 1
                """
            )
        )
    ).first()
    if row:
        return int(row[0]), False

    row2 = (await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))).first()
    if not row2:
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Phase 3 出库合同测试")
    return int(row2[0]), True


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


@pytest.mark.asyncio
async def test_phase3_outbound_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（出库链路）：
    - 先用 StockService.adjust(delta>0) 造库存（写 ledger + stocks_lot）
    - 再用 OutboundService.commit 出库（写 ledger + stocks_lot + snapshot 尾门）
    - 最后用三账校验器兜底复验：ledger(ref/ref_line) + stocks_lot + snapshot(today) 一致
    """
    utc = timezone.utc
    now = datetime.now(utc)

    stock_svc = StockService()
    outbound_svc = OutboundService(stock_svc=stock_svc)

    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item_for_stock_in(session)
    batch_code = "B-PH3-OUT"

    # 入库造数：给足库存，避免出库不足
    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    ref_in = "UT:PH3:IN"
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        delta=10,  # 入库 +10
        reason="RECEIPT",
        ref=ref_in,
        ref_line=1,
        occurred_at=now,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
        trace_id="PH3-UT-TRACE-OUT",
        meta={"sub_reason": "UT_STOCK_IN"},
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

    # 双保险：再跑一次快照 + 三账校验（只对本次 touched key）
    await run_snapshot(session)
    await verify_receive_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=str(order_id),
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": -ship_qty,  # 出库 delta 为负
                "ref": str(order_id),
                "ref_line": 1,
            }
        ],
        at=now,
    )
