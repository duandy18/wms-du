# tests/services/test_order_rma_and_reconcile.py
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_reconcile_service import OrderReconcileService
from app.services.order_service import OrderService
from app.services.stock_service import StockService

UTC = timezone.utc


async def _insert_confirmed_order_return_receipt(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    item_id: int,
    qty_received: int,
    batch_code: str,
    occurred_at: datetime,
    trace_id: str,
) -> int:
    """
    退货终态口径：用 confirmed InboundReceipt 事实表达 returned。
    - inbound_receipts.source_type='ORDER'
    - inbound_receipts.source_id=order_id
    - inbound_receipts.status='CONFIRMED'
    - inbound_receipt_lines.qty_received 作为 returned_qty（按 item_id 聚合）

    Phase5+ 护栏：
    - inbound_receipts.ref 全局唯一 → 同一订单多张 RMA receipt 必须使用唯一 ref
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

    await session.execute(
        text(
            """
            INSERT INTO inbound_receipt_lines (
                receipt_id,
                line_no,
                po_line_id,
                item_id,
                item_name,
                item_sku,
                batch_code,
                production_date,
                expiry_date,
                qty_received,
                units_per_case,
                qty_units,
                unit_cost,
                line_amount,
                remark,
                created_at,
                updated_at
            )
            VALUES (
                :rid,
                1,
                NULL,
                :item_id,
                'UT-ITEM',
                NULL,
                :batch_code,
                :production_date,
                NULL,
                :qty_received,
                1,
                :qty_units,
                NULL,
                NULL,
                'UT-RMA-LINE',
                NOW(),
                NOW()
            )
            """
        ),
        {
            "rid": int(receipt_id),
            "item_id": int(item_id),
            "batch_code": str(batch_code),
            "production_date": date.today(),
            "qty_received": int(qty_received),
            "qty_units": int(qty_received),
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
            {"item_id": 1, "qty": 2},
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
        item_id=1,
        warehouse_id=1,
        delta=2,
        reason=MovementType.INBOUND,
        ref=f"IN-{order_ref}",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="RMA-BATCH-1",
        production_date=date.today(),
    )

    # 3) 模拟发货 shipped=2（只统计负数 delta，用于 shipped 计算）
    await stock_svc.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=-2,
        reason=MovementType.SHIP,
        ref=order_ref,
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="RMA-BATCH-1",
        production_date=date.today(),
    )

    # 4) 写入一张 confirmed Receipt：returned=2（remaining 应为 0）
    await _insert_confirmed_order_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=1,
        qty_received=2,
        batch_code="RMA-BATCH-1",
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
        item_id=1,
        qty_received=1,
        batch_code="RMA-BATCH-1",
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
    """
    platform = "PDD"
    shop_id = "RMA_TEST_SHOP2"
    ext_order_no = "RMA-TEST-002"
    trace_id = "TRACE-RMA-TEST-002"

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
            {"item_id": 1, "qty": 2},
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
        item_id=1,
        warehouse_id=1,
        delta=2,
        reason=MovementType.INBOUND,
        ref=f"IN-{order_ref}",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="RMA-BATCH-2",
        production_date=date.today(),
    )
    await stock_svc.adjust(
        session=session,
        item_id=1,
        warehouse_id=1,
        delta=-2,
        reason=MovementType.SHIP,
        ref=order_ref,
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="RMA-BATCH-2",
        production_date=date.today(),
    )

    # 3) 写入 returned=1 的 confirmed Receipt
    await _insert_confirmed_order_return_receipt(
        session,
        order_id=order_id,
        warehouse_id=1,
        item_id=1,
        qty_received=1,
        batch_code="RMA-BATCH-2",
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
    )

    # 4) 对账视角检查
    recon = OrderReconcileService(session)
    result_recon = await recon.reconcile_order(order_id)
    assert len(result_recon.lines) == 1
    lf = result_recon.lines[0]
    assert lf.item_id == 1
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
            {"oid": order_id, "iid": 1},
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
