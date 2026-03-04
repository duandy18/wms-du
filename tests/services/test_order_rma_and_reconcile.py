# tests/services/test_order_rma_and_reconcile.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_reconcile_service import OrderReconcileService
from app.services.order_service import OrderService
from app.services.stock.lots import ensure_internal_lot_singleton
from app.services.stock_service import StockService

UTC = timezone.utc


async def _item_batch_mode_is_required(session: AsyncSession, *, item_id: int) -> bool:
    """
    Phase M 第一阶段：测试不再读取 has_shelf_life（镜像字段）。
    批次受控唯一真相源：items.expiry_policy == 'REQUIRED'
    """
    row = (
        await session.execute(
            text(
                """
                SELECT expiry_policy
                  FROM items
                 WHERE id = :iid
                 LIMIT 1
                """
            ),
            {"iid": int(item_id)},
        )
    ).first()
    if row is None:
        return False
    return str(row[0] or "").strip().upper() == "REQUIRED"


async def _pick_base_uom_and_ratio(session: AsyncSession, *, item_id: int) -> Tuple[int, int]:
    """
    终态：收货行必须显式落 uom_id + ratio_to_base_snapshot + qty_base。
    这里选 base uom（is_base=true），保证测试稳定。
    """
    row = await session.execute(
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
    r = row.first()
    assert r is not None, {"msg": "item has no base uom", "item_id": int(item_id)}
    return int(r[0]), int(r[1])


async def _ensure_supplier_lot(session: AsyncSession, *, warehouse_id: int, item_id: int, code: str) -> int:
    """
    SUPPLIER lot（终态合同）：
    - identity = (warehouse_id, item_id, lot_code_key)
    - unique index = UNIQUE(warehouse_id,item_id,lot_code_key) WHERE lot_code IS NOT NULL
    - lot_code 为展示码；lot_code_key 为 normalize(key) 防漂移（trim+upper）
    - 必填快照从 items 取值。
    """
    code_raw = str(code).strip()
    assert code_raw, {"msg": "empty lot_code", "warehouse_id": warehouse_id, "item_id": item_id}
    code_key = code_raw.upper()

    r = await session.execute(
        text(
            """
            INSERT INTO lots(
              warehouse_id,
              item_id,
              lot_code_source,
              lot_code,
              lot_code_key,
              source_receipt_id,
              source_line_no,
              item_lot_source_policy_snapshot,
              item_expiry_policy_snapshot,
              item_derivation_allowed_snapshot,
              item_uom_governance_enabled_snapshot,
              item_shelf_life_value_snapshot,
              item_shelf_life_unit_snapshot,
              created_at
            )
            SELECT
              :w,
              it.id,
              'SUPPLIER',
              :code_raw,
              :code_key,
              NULL,
              NULL,
              it.lot_source_policy,
              it.expiry_policy,
              it.derivation_allowed,
              it.uom_governance_enabled,
              it.shelf_life_value,
              it.shelf_life_unit,
              now()
            FROM items it
            WHERE it.id = :i
            ON CONFLICT (warehouse_id, item_id, lot_code_key)
            WHERE lot_code IS NOT NULL
            DO NOTHING
            RETURNING id
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code_raw": code_raw, "code_key": code_key},
    )
    got = r.scalar_one_or_none()
    if got is not None:
        return int(got)

    # select-after-race / already exists
    r2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code_key = :code_key
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code_key": code_key},
    )
    got2 = r2.scalar_one_or_none()
    assert got2 is not None, {
        "msg": "failed to ensure supplier lot",
        "warehouse_id": warehouse_id,
        "item_id": item_id,
        "code_raw": code_raw,
        "code_key": code_key,
    }
    return int(got2)


async def _ensure_internal_lot_for_receipt(session: AsyncSession, *, warehouse_id: int, item_id: int, receipt_id: int) -> int:
    """
    INTERNAL lot（终态合同）：
    - 单例：每 (warehouse_id,item_id) 只有一个 INTERNAL lot
      UNIQUE (warehouse_id,item_id) WHERE lot_code_source='INTERNAL' AND lot_code IS NULL
    - lot_code 必须为 NULL
    - source_receipt_id/source_line_no 作为可选 provenance，要求成对填充（这里用当前 receipt + line_no=1）
    """
    return await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        source_receipt_id=int(receipt_id),
        source_line_no=1,
    )


async def _insert_confirmed_order_return_receipt(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    item_id: int,
    qty_received: int,
    batch_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
    occurred_at: datetime,
    trace_id: str,
) -> int:
    """
    退货终态口径：用 confirmed InboundReceipt 事实表达 returned。

    终态写入：
    - inbound_receipts: source_type='ORDER', source_id=order_id, status='CONFIRMED'
    - inbound_receipt_lines: 使用终态列（uom_id + qty_input + ratio_to_base_snapshot + qty_base + lot_id + warehouse_id）
      且 receipt_status_snapshot='CONFIRMED'（lot_id 必填）
    - batch_code 仅作为 lot_code_input 展示/输入码；lot_id 才是结构锚点
    """
    ref = f"RMA-ORD-{order_id}-{trace_id}-{int(occurred_at.timestamp()*1000)}"

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
                        'ORDER',
                        :order_id,
                        :ref,
                        :trace_id,
                        'CONFIRMED',
                        'UT-RMA',
                        :occurred_at,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                    """
                ),
                {
                    "warehouse_id": int(warehouse_id),
                    "order_id": int(order_id),
                    "ref": str(ref),
                    "trace_id": str(trace_id),
                    "occurred_at": occurred_at,
                },
            )
        ).scalar_one()
    )

    uom_id, ratio = await _pick_base_uom_and_ratio(session, item_id=int(item_id))
    qty_input = int(qty_received)
    qty_base = int(qty_input) * int(ratio)

    if batch_code is not None:
        lot_id = await _ensure_supplier_lot(session, warehouse_id=int(warehouse_id), item_id=int(item_id), code=str(batch_code))
        lot_code_input = str(batch_code)
    else:
        lot_id = await _ensure_internal_lot_for_receipt(
            session, warehouse_id=int(warehouse_id), item_id=int(item_id), receipt_id=int(receipt_id)
        )
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
                :item_id,
                :production_date,
                :expiry_date,
                NULL,
                NULL,
                'UT-RMA-LINE',
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
            "item_id": int(item_id),
            "production_date": production_date,
            "expiry_date": expiry_date,
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
async def test_rma_cannot_exceed_shipped(session: AsyncSession) -> None:
    """
    验证 RMA 上限规则：

      remaining = max(min(ordered, shipped) - returned, 0)

    场景：
      - 下单 qty=2（item_id=1）；
      - 入库 + 发货 shipped=2（ref=ORD:...）；
      - 写入一张 confirmed Receipt returned=2 → remaining=0；
      - 再试图追加 returned=1（第二张 Receipt） -> returned>shipped 的问题被识别出来。
    """
    platform = "PDD"
    shop_id = "RMA_TEST_SHOP"
    ext_order_no = "RMA-TEST-001"
    trace_id = "TRACE-RMA-TEST-001"

    item_id = 1
    required = await _item_batch_mode_is_required(session, item_id=item_id)

    if required:
        bc: Optional[str] = "RMA-BATCH-1"
        pd = date.today()
        ed = None
    else:
        bc = None
        pd = None
        ed = None

    # 1) 用服务层落一张订单（2 件 item_id=1）
    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(UTC),
        buyer_name="RMA 测试用户",
        buyer_phone="13800000000",
        order_amount=20,
        pay_amount=20,
        items=[
            {"item_id": item_id, "qty": 2},
        ],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])
    order_ref = result["ref"]  # 形如 ORD:PDD:SHOP:EXT

    stock_svc = StockService()

    # 2) 先做一笔入库，保证库存足够
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=2,
        reason=MovementType.INBOUND,
        ref=f"IN-{order_ref}",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
    )

    # 3) 模拟发货 shipped=2（只统计负数 delta，用于 shipped 计算）
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=-2,
        reason=MovementType.SHIP,
        ref=order_ref,
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
    )

    # 4) 写入一张 confirmed Receipt：returned=2（remaining 应为 0）
    await _insert_confirmed_order_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_received=2,
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
    )

    recon = OrderReconcileService(session)
    result_recon = await recon.reconcile_order(order_id)
    assert len(result_recon.lines) == 1
    lf = result_recon.lines[0]
    assert lf.qty_ordered == 2
    assert lf.qty_shipped == 2
    assert lf.qty_returned == 2
    assert lf.remaining_refundable == 0

    # 5) 再追加一张 returned=1 的 Receipt → returned=3 > shipped=2
    await _insert_confirmed_order_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_received=1,
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
    )

    result_recon2 = await recon.reconcile_order(order_id)
    assert len(result_recon2.lines) == 1
    lf2 = result_recon2.lines[0]
    assert lf2.qty_ordered == 2
    assert lf2.qty_shipped == 2
    assert lf2.qty_returned == 3
    assert lf2.remaining_refundable == 0
    assert any("returned(3) > shipped(2)" in x for x in result_recon2.issues)


@pytest.mark.asyncio
async def test_rma_receipt_updates_counters_and_status(session: AsyncSession) -> None:
    """
    验证完整链路（Receipt 终态口径）：

      - 订单 qty=2（item_id=1）；
      - 入库 + 发货 shipped=2；
      - 写入 returned=1 的 confirmed Receipt；
      - OrderReconcileService 能算出 ordered=2, shipped=2, returned=1, remaining=1；
      - apply_counters 将 shipped_qty=2 / returned_qty=1 写回 order_items；
      - orders.status 变为 PARTIALLY_RETURNED。

    说明：
      - returned 的事实源不再是旧执行层 commit，而是 confirmed InboundReceipt。

    Phase 1A 批次两态：
      - NONE：batch_code=NULL 且 production/expiry=NULL
      - REQUIRED：batch_code 非空；日期可按需要填写
    """
    platform = "PDD"
    shop_id = "RMA_TEST_SHOP2"
    ext_order_no = "RMA-TEST-002"
    trace_id = "TRACE-RMA-TEST-002"

    item_id = 1
    required = await _item_batch_mode_is_required(session, item_id=item_id)

    if required:
        bc: Optional[str] = "RMA-BATCH-2"
        pd = date.today()
        ed = None
    else:
        bc = None
        pd = None
        ed = None

    # 1) 下单 qty=2（item_id=1）
    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(UTC),
        buyer_name="RMA 测试用户2",
        buyer_phone="13900000000",
        order_amount=20,
        pay_amount=20,
        items=[
            {"item_id": item_id, "qty": 2},
        ],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])
    order_ref = result["ref"]

    stock_svc = StockService()

    # 2) 入库 + 发货 shipped=2
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=2,
        reason=MovementType.INBOUND,
        ref=f"IN-{order_ref}",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
    )
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=-2,
        reason=MovementType.SHIP,
        ref=order_ref,
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
    )

    # 3) 写入 returned=1 的 confirmed Receipt
    await _insert_confirmed_order_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_received=1,
        batch_code=bc,
        production_date=pd,
        expiry_date=ed,
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
    )

    # 4) 对账视角检查
    recon = OrderReconcileService(session)
    result_recon = await recon.reconcile_order(order_id)
    assert len(result_recon.lines) == 1
    lf = result_recon.lines[0]
    assert lf.item_id == item_id
    assert lf.qty_ordered == 2
    assert lf.qty_shipped == 2
    assert lf.qty_returned == 1
    assert lf.remaining_refundable == 1

    # 5) apply_counters：写回 order_items，并触发订单状态演进（若实现如此）
    await recon.apply_counters(order_id)

    row = (
        await session.execute(
            text(
                """
                SELECT shipped_qty, returned_qty
                  FROM order_items
                 WHERE order_id = :oid
                   AND item_id = :iid
                 LIMIT 1
                """
            ),
            {"oid": order_id, "iid": item_id},
        )
    ).first()
    assert row is not None
    shipped_qty, returned_qty = row
    assert shipped_qty == 2
    assert returned_qty == 1

    row2 = (
        await session.execute(
            text(
                """
                SELECT status
                  FROM orders
                 WHERE id = :oid
                 LIMIT 1
                """
            ),
            {"oid": order_id},
        )
    ).first()
    assert row2 is not None
    status = row2[0]
    assert status == "PARTIALLY_RETURNED"
