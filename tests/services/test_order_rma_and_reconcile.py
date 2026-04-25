# tests/services/test_order_rma_and_reconcile.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.oms.orders.services.order_reconcile_service import OrderReconcileService
from app.oms.services.order_service import OrderService
from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl

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
    SUPPLIER lot（当前终态合同）：
    - REQUIRED lot 身份 = (warehouse_id, item_id, production_date)
    - lot_code 只保留为展示/输入/追溯属性
    - 必填快照从 items 取值

    ✅ 终态收口：禁止 tests 直接 INSERT INTO lots
    -> 统一走 app.wms.stock.services.lots.ensure_lot_full
    """
    code_raw = str(code).strip()
    assert code_raw, {"msg": "empty lot_code", "warehouse_id": warehouse_id, "item_id": item_id}

    required = await _item_batch_mode_is_required(session, item_id=int(item_id))
    production_date = date.today() if required else None
    expiry_date = (production_date + timedelta(days=30)) if production_date is not None else None

    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(code_raw),
        production_date=production_date,
        expiry_date=expiry_date,
    )
    return int(lot_id)


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


async def _ensure_stock_lot_for_adjust(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> int:
    """
    测试造数专用：把 lot 解析提前显式化。
    """
    if batch_code is not None:
        return await _ensure_supplier_lot(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            code=str(batch_code),
        )

    return int(
        await ensure_internal_lot_singleton(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            source_receipt_id=None,
            source_line_no=None,
        )
    )


async def _write_stock_delta_for_test(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
    delta: int,
    reason: MovementType,
    ref: str,
    ref_line: int,
    occurred_at: datetime,
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> None:
    lot_id = await _ensure_stock_lot_for_adjust(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=int(delta),
        reason=reason,
        ref=str(ref),
        ref_line=int(ref_line),
        occurred_at=occurred_at,
        meta=None,
        batch_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )


async def _insert_released_return_receipt(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    item_id: int,
    qty_returned: int,
    batch_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
    occurred_at: datetime,
    trace_id: str,
) -> int:
    """
    退货终态口径：用 released RETURN_ORDER 收货单与收货执行事实表达 returned。

    终态写入：
    - inbound_receipts: source_type='RETURN_ORDER', source_doc_id=order_id, status='RELEASED'
    - inbound_receipt_lines: 使用终态列（item_uom_id + planned_qty + ratio_to_base_snapshot）
    - wms_inbound_operation_lines.qty_base 作为 returned 聚合的执行事实
    - batch_no 仅作为展示/输入码；lot_id 才是结构锚点
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
                        counterparty_name_snapshot,
                        source_type,
                        source_doc_id,
                        source_doc_no_snapshot,
                        receipt_no,
                        status,
                        remark,
                        created_by,
                        released_at,
                        created_at,
                        updated_at,
                        warehouse_name_snapshot
                    )
                    VALUES (
                        :warehouse_id,
                        NULL,
                        NULL,
                        'RETURN_ORDER',
                        :order_id,
                        NULL,
                        :ref,
                        'RELEASED',
                        'UT-RMA',
                        NULL,
                        :occurred_at,
                        NOW(),
                        NOW(),
                        'WH-1'
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
    qty_input = int(qty_returned)
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
                inbound_receipt_id,
                line_no,
                source_line_id,
                item_id,
                item_uom_id,
                planned_qty,
                item_name_snapshot,
                item_spec_snapshot,
                uom_name_snapshot,
                ratio_to_base_snapshot,
                remark,
                created_at,
                updated_at
            )
            VALUES (
                :rid,
                1,
                NULL,
                :item_id,
                :uom_id,
                :qty_input,
                (SELECT name FROM items WHERE id = :item_id),
                (SELECT spec FROM items WHERE id = :item_id),
                (SELECT COALESCE(NULLIF(display_name, ''), NULLIF(uom, '')) FROM item_uoms WHERE id = :uom_id),
                :ratio,
                'UT-RMA-LINE',
                NOW(),
                NOW()
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

    op_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO wms_inbound_operations (
                        receipt_no_snapshot,
                        warehouse_id,
                        warehouse_name_snapshot,
                        supplier_id,
                        supplier_name_snapshot,
                        operator_id,
                        operator_name_snapshot,
                        operated_at,
                        remark
                    )
                    VALUES (
                        :receipt_no,
                        :warehouse_id,
                        'WH-1',
                        NULL,
                        NULL,
                        NULL,
                        NULL,
                        :occurred_at,
                        'UT-RMA'
                    )
                    RETURNING id
                    """
                ),
                {
                    "receipt_no": str(ref),
                    "warehouse_id": int(warehouse_id),
                    "occurred_at": occurred_at,
                },
            )
        ).scalar_one()
    )

    await session.execute(
        text(
            """
            INSERT INTO wms_inbound_operation_lines (
                wms_inbound_operation_id,
                receipt_line_no_snapshot,
                item_id,
                item_name_snapshot,
                item_spec_snapshot,
                actual_item_uom_id,
                actual_uom_name_snapshot,
                actual_ratio_to_base_snapshot,
                actual_qty_input,
                qty_base,
                batch_no,
                production_date,
                expiry_date,
                lot_id,
                remark
            )
            VALUES (
                :op_id,
                1,
                :item_id,
                (SELECT name FROM items WHERE id = :item_id),
                (SELECT spec FROM items WHERE id = :item_id),
                :uom_id,
                (SELECT COALESCE(NULLIF(display_name, ''), NULLIF(uom, '')) FROM item_uoms WHERE id = :uom_id),
                :ratio,
                :qty_input,
                :qty_base,
                :lot_code_input,
                :production_date,
                :expiry_date,
                :lot_id,
                'UT-RMA-OP-LINE'
            )
            """
        ),
        {
            "op_id": int(op_id),
            "item_id": int(item_id),
            "uom_id": int(uom_id),
            "ratio": int(ratio),
            "qty_input": int(qty_input),
            "qty_base": int(qty_base),
            "lot_code_input": lot_code_input,
            "production_date": production_date,
            "expiry_date": expiry_date,
            "lot_id": int(lot_id),
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
      - 写入一张 released 退货入库单 returned=2 → remaining=0；
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
        ed = pd + timedelta(days=30)
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

    # 2) 先做一笔入库，保证库存足够
    await _write_stock_delta_for_test(
        session,
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
    await _write_stock_delta_for_test(
        session,
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

    # 4) 写入一张 released 退货入库单：returned=2（remaining 应为 0）
    await _insert_released_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_returned=2,
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
    await _insert_released_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_returned=1,
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
      - 写入 returned=1 的 released 退货入库单；
      - OrderReconcileService 能算出 ordered=2, shipped=2, returned=1, remaining=1；
      - apply_counters 将 shipped_qty=2 / returned_qty=1 写回 order_items；
      - orders.status 变为 PARTIALLY_RETURNED。

    说明：
      - returned 的事实源不再是旧执行层 commit，而是 released RETURN_ORDER 收货单 + 收货执行事实。

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
        ed = pd + timedelta(days=30)
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

    # 2) 入库 + 发货 shipped=2
    await _write_stock_delta_for_test(
        session,
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
    await _write_stock_delta_for_test(
        session,
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

    # 3) 写入 returned=1 的 released 退货入库单
    await _insert_released_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=item_id,
        qty_returned=1,
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
