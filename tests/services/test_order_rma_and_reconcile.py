# tests/services/test_order_rma_and_reconcile.py
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.schemas.receive_task import OrderReturnLineIn
from app.services.order_reconcile_service import OrderReconcileService
from app.services.order_service import OrderService
from app.services.receive_task_service import ReceiveTaskService
from app.services.stock_service import StockService

UTC = timezone.utc


@pytest.mark.asyncio
async def test_rma_cannot_exceed_shipped(session: AsyncSession) -> None:
    """
    验证 RMA 上限规则：

      remaining = max(min(ordered, shipped) - returned, 0)

    场景：
      - 下单 qty=2（item_id=1）；
      - 入库 + 发货 shipped=2（ref=ORD:...）；
      - 第一次创建 RMA 任务 qty=2 → 允许（remaining = 2）；
      - 第二次再创建 RMA 任务 qty=1 → 拒绝（remaining 已为 0）。
    """
    # 确保环境中没有历史 RMA 任务污染
    await session.execute(text("DELETE FROM receive_task_lines"))
    await session.execute(text("DELETE FROM receive_tasks"))

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
        scope="PROD",
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
        scope="PROD",
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

    rma_svc = ReceiveTaskService()

    # 4) 第一次创建 RMA 任务：qty=2，应当允许（remaining = 2）
    lines_ok = [OrderReturnLineIn(item_id=1, qty=2)]
    task_ok = await rma_svc.create_for_order(
        session,
        order_id=order_id,
        warehouse_id=1,
        lines=lines_ok,
    )
    assert task_ok.id is not None
    assert len(task_ok.lines) == 1
    assert task_ok.lines[0].expected_qty == 2

    # 5) 第二次创建 RMA 任务：qty=1，应当报错（remaining 已消耗完）
    lines_exceed = [OrderReturnLineIn(item_id=1, qty=1)]
    with pytest.raises(ValueError) as excinfo:
        await rma_svc.create_for_order(
            session,
            order_id=order_id,
            warehouse_id=1,
            lines=lines_exceed,
        )

    msg = str(excinfo.value)
    # 提示中应包含原始数量 / 已发货 / 已退 / 本次请求 / 剩余可退等信息
    assert "退货数量超出可退上限" in msg
    assert "原始数量=2" in msg
    assert "已发货=2" in msg
    assert "本次请求=1" in msg
    assert "剩余可退=0" in msg


@pytest.mark.asyncio
async def test_rma_commit_updates_counters_and_status(session: AsyncSession) -> None:
    """
    验证完整链路：

      - 订单 qty=2（item_id=1）；
      - 入库 + 发货 shipped=2；
      - 创建 RMA 任务 qty=1 + 扫码 + commit；
      - OrderReconcileService 能算出 ordered=2, shipped=2, returned=1, remaining=1；
      - apply_counters 将 shipped_qty=2 / returned_qty=1 写回 order_items；
      - orders.status 变为 PARTIALLY_RETURNED。

    注意：
      - 当前实现要求：任何 scanned_qty != 0 的行，在 commit 前必须具备：
          * 非空 batch_code
          * 至少一个日期（production_date 或 expiry_date）
        因此本测试在 record_scan 时必须补齐 batch + 日期。
    """
    # 确保环境中没有历史 RMA 任务污染
    await session.execute(text("DELETE FROM receive_task_lines"))
    await session.execute(text("DELETE FROM receive_tasks"))

    platform = "PDD"
    shop_id = "RMA_TEST_SHOP2"
    ext_order_no = "RMA-TEST-002"
    trace_id = "TRACE-RMA-TEST-002"

    # 1) 下单 qty=2（item_id=1，同样使用已有的测试商品）
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

    # 2) 先做一笔入库，保证库存足够
    await stock_svc.adjust(
        session=session,
        scope="PROD",
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

    # 3) 模拟发货 shipped=2（只统计负数 delta，用于 shipped 计算）
    await stock_svc.adjust(
        session=session,
        scope="PROD",
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

    rma_svc = ReceiveTaskService()

    # 4) 创建 RMA 任务 qty=1
    task = await rma_svc.create_for_order(
        session,
        order_id=order_id,
        warehouse_id=1,
        lines=[OrderReturnLineIn(item_id=1, qty=1)],
    )

    # 模拟扫码：scanned_qty=1，补齐 batch_code + 至少一个日期（与 commit 的硬校验一致）
    await rma_svc.record_scan(
        session,
        task_id=task.id,
        item_id=1,
        qty=1,
        batch_code="RMA-BATCH-2",
        production_date=date.today(),
        expiry_date=None,
    )

    # 5) commit：会写入 ledger + 更新任务 + apply_counters + 更新订单状态
    await rma_svc.commit(
        session,
        task_id=task.id,
        trace_id=trace_id,
    )

    # 6) 对账视角检查
    recon = OrderReconcileService(session)
    result_recon = await recon.reconcile_order(order_id)
    assert len(result_recon.lines) == 1
    lf = result_recon.lines[0]
    assert lf.item_id == 1
    assert lf.qty_ordered == 2
    assert lf.qty_shipped == 2
    assert lf.qty_returned == 1
    assert lf.remaining_refundable == 1

    # 7) counters 已写回 order_items
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

    # 8) 订单状态应为 PARTIALLY_RETURNED
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
