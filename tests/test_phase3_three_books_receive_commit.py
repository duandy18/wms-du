# tests/test_phase3_three_books_receive_commit.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.services.stock.lots import ensure_internal_lot_singleton, ensure_lot_full
from app.services.stock_service import StockService
from app.services.three_books_consistency import verify_receive_commit_three_books


async def _pick_test_item(session: AsyncSession) -> tuple[int, bool]:
    """
    尽量挑一个不需要有效期管理的商品（避免被业务校验噪音卡住）。
    若找不到，则退回任意一个 item（expiry_policy=REQUIRED 也行，测试会显式填 expiry_date）。
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
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Phase 3 合同测试")
    return int(row2[0]), True


async def _ensure_base_uom(session: AsyncSession, *, item_id: int) -> Tuple[int, int]:
    """
    终态：receipt_line 必须写入 uom_id + ratio_to_base_snapshot + qty_base。
    优先取 is_base=true；若该 item 没有 item_uoms，则补一条最小 base uom（PCS, ratio=1）。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id, ratio_to_base
                  FROM item_uoms
                 WHERE item_id = :i AND is_base = true
                 ORDER BY id
                 LIMIT 1
                """
            ),
            {"i": int(item_id)},
        )
    ).first()
    if row is not None:
        return int(row[0]), int(row[1])

    # 缺失时补齐最小合法 base uom（不依赖外部 seed 的稳定性）
    await session.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :i, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            """
        ),
        {"i": int(item_id)},
    )

    row2 = (
        await session.execute(
            text(
                """
                SELECT id, ratio_to_base
                  FROM item_uoms
                 WHERE item_id = :i AND is_base = true
                 ORDER BY id
                 LIMIT 1
                """
            ),
            {"i": int(item_id)},
        )
    ).first()
    assert row2 is not None, {"msg": "failed to ensure base uom", "item_id": int(item_id)}
    return int(row2[0]), int(row2[1])


async def _ensure_supplier_lot(session: AsyncSession, *, warehouse_id: int, item_id: int, lot_code: str) -> int:
    """
    确保 SUPPLIER lot 存在，返回 lot_id。

    ✅ 终态收口：禁止 tests 直接 INSERT INTO lots
    -> 统一走 app/services/stock/lots.py: ensure_lot_full
    """
    code = str(lot_code).strip()
    if not code:
        raise ValueError("lot_code required for supplier lot")

    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(code),
        production_date=None,
        expiry_date=None,
    )
    return int(lot_id)


async def _ensure_internal_lot_for_receipt(
    session: AsyncSession, *, warehouse_id: int, item_id: int, receipt_id: int
) -> int:
    """
    INTERNAL lot：lot_code NULL。

    ✅ 终态收口：禁止 tests 直接 INSERT INTO lots
    -> 统一走 app/services/stock/lots.py: ensure_internal_lot_singleton

    这里仍然把 receipt_id/line_no 作为 provenance 成对传入，满足成对可选规则。
    """
    lot_id = await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        source_receipt_id=int(receipt_id),
        source_line_no=1,
    )
    return int(lot_id)


async def _insert_confirmed_receipt_with_line(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
    qty_received: int,
    occurred_at: datetime,
    trace_id: str,
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> int:
    """
    终态 receipt 事实（CONFIRMED）：
    - inbound_receipt_lines 使用终态列（uom_id + qty_input + ratio_to_base_snapshot + qty_base + lot_id + warehouse_id）
    - lot_id 在 CONFIRMED 状态下必须非空
    """
    ref = "RCPT-PH3-UT"

    receipt_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO inbound_receipts (
                        warehouse_id,
                        supplier_id,
                        supplier_name,
                        source_type,
                        source_id,
                        ref,
                        trace_id,
                        status,
                        remark,
                        occurred_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :warehouse_id,
                        NULL,
                        NULL,
                        'PO',
                        NULL,
                        :ref,
                        :trace_id,
                        'CONFIRMED',
                        'UT-PH3',
                        :occurred_at,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                    """
                ),
                {
                    "warehouse_id": int(warehouse_id),
                    "ref": str(ref),
                    "trace_id": str(trace_id),
                    "occurred_at": occurred_at,
                },
            )
        ).scalar_one()
    )

    uom_id, ratio = await _ensure_base_uom(session, item_id=int(item_id))
    qty_input = int(qty_received)
    qty_base = int(qty_input) * int(ratio)

    if batch_code is not None:
        lot_id = await _ensure_supplier_lot(session, warehouse_id=int(warehouse_id), item_id=int(item_id), lot_code=str(batch_code))
        lot_code_input = str(batch_code)
    else:
        lot_id = await _ensure_internal_lot_for_receipt(session, warehouse_id=int(warehouse_id), item_id=int(item_id), receipt_id=int(receipt_id))
        lot_code_input = None

    await session.execute(
        text(
            """
            INSERT INTO inbound_receipt_lines (
                receipt_id,
                line_no,
                po_line_id,
                item_id,
                production_date,
                expiry_date,
                unit_cost,
                line_amount,
                remark,
                created_at,
                updated_at,
                lot_id,
                warehouse_id,
                uom_id,
                qty_input,
                ratio_to_base_snapshot,
                qty_base,
                receipt_status_snapshot,
                lot_code_input
            )
            VALUES (
                :rid,
                1,
                NULL,
                :iid,
                :pd,
                :ed,
                NULL,
                NULL,
                'UT-PH3-LINE',
                NOW(),
                NOW(),
                :lot_id,
                :warehouse_id,
                :uom_id,
                :qty_input,
                :ratio,
                :qty_base,
                'CONFIRMED',
                :lot_code_input
            )
            """
        ),
        {
            "rid": int(receipt_id),
            "iid": int(item_id),
            "pd": production_date,
            "ed": expiry_date,
            "lot_id": int(lot_id),
            "warehouse_id": int(warehouse_id),
            "uom_id": int(uom_id),
            "qty_input": int(qty_input),
            "ratio": int(ratio),
            "qty_base": int(qty_base),
            "lot_code_input": lot_code_input,
        },
    )
    await session.flush()
    return receipt_id


@pytest.mark.asyncio
async def test_phase3_receive_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（终态口径）：

    - 以 Receipt(CONFIRMED) 作为事实锚点（终态不再有旧执行层）
    - 以 StockService.adjust(INBOUND) 作为“入库落账动作”写入 ledger+stocks_lot
    - snapshot(today) == stocks_lot（至少对 touched keys）
    - verify_receive_commit_three_books 对 touched effects 做三账一致性校验

    Phase 1A 批次两态（真相源：items.expiry_policy）：
    - expiry_policy=NONE：batch_code=NULL 且 production/expiry=NULL；库存聚合到无批次槽位（INTERNAL lot_code NULL）
    - expiry_policy=REQUIRED：batch_code 非空；日期按测试显式填写
    """
    stock_svc = StockService()
    utc = timezone.utc
    now = datetime.now(utc)

    item_id, may_need_expiry = await _pick_test_item(session)

    scanned_qty = 5  # base-unit

    if may_need_expiry:
        batch_code: Optional[str] = "B-PH3"
        prod = now.date()
        exp = prod + timedelta(days=30)
    else:
        # NONE：三空（Phase 1A 红线）
        batch_code = None
        prod = None
        exp = None

    # 1) 写入 Receipt 事实（终态：CONFIRMED）
    await _insert_confirmed_receipt_with_line(
        session,
        warehouse_id=1,
        item_id=item_id,
        batch_code=batch_code,
        qty_received=scanned_qty,
        occurred_at=now,
        trace_id="PH3-UT-TRACE",
        production_date=prod,
        expiry_date=exp,
    )

    # 2) 写入入库动作（ledger+stocks_lot）
    ref = "RCPT-PH3-UT"
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=scanned_qty,
        reason=MovementType.INBOUND,
        ref=ref,
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
    )

    # 3) 双保险：独立跑快照 + 三账一致性校验
    # 终态：effects 必须带 lot_id（lot-only world），从 ledger 反查本次 ref/ref_line 的 lot_id
    row = await session.execute(
        text(
            """
            SELECT lot_id
              FROM stock_ledger
             WHERE warehouse_id = :w
               AND item_id = :i
               AND ref = :ref
               AND ref_line = :rl
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"w": 1, "i": int(item_id), "ref": str(ref), "rl": 1},
    )
    lot_id = row.scalar_one_or_none()
    assert lot_id is not None, {"msg": "expected ledger row to provide lot_id", "ref": ref, "ref_line": 1, "item_id": item_id}

    await run_snapshot(session)
    await verify_receive_commit_three_books(
        session,
        warehouse_id=1,
        ref=ref,
        effects=[
            {
                "warehouse_id": 1,
                "item_id": item_id,
                "batch_code": batch_code,
                "lot_id": int(lot_id),
                "qty": scanned_qty,
                "ref": ref,
                "ref_line": 1,
            }
        ],
        at=now,
    )
