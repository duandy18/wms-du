# app/services/receive_task_create.py
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.schemas.receive_task import OrderReturnLineIn

from app.services.receive_task_loaders import (
    load_order_item_qty_map,
    load_order_returned_qty_map,
    load_order_shipped_qty_map,
    load_po,
)
from app.services.receive_task_query import get_with_lines


async def create_for_po(
    session: AsyncSession,
    *,
    po_id: int,
    warehouse_id: Optional[int] = None,
    include_fully_received: bool = False,
) -> ReceiveTask:
    po = await load_po(session, po_id)
    wh_id = warehouse_id or po.warehouse_id

    task = ReceiveTask(
        source_type="PO",
        source_id=po.id,
        po_id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier_name or po.supplier,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"from PO-{po.id}",
    )
    session.add(task)
    await session.flush()

    lines_to_create: list[ReceiveTaskLine] = []
    for line in po.lines or []:
        remaining = line.qty_ordered - line.qty_received
        if remaining <= 0 and not include_fully_received:
            continue

        rtl = ReceiveTaskLine(
            task_id=task.id,
            po_line_id=line.id,
            item_id=line.item_id,
            item_name=line.item_name,
            item_sku=line.item_sku,
            category=line.category,
            spec_text=line.spec_text,
            base_uom=line.base_uom,
            purchase_uom=line.purchase_uom,
            units_per_case=line.units_per_case,
            batch_code=None,
            production_date=None,
            expiry_date=None,
            expected_qty=remaining if remaining > 0 else 0,
            scanned_qty=0,
            committed_qty=None,
            status="DRAFT",
        )
        lines_to_create.append(rtl)

    if not lines_to_create:
        raise ValueError(f"采购单 {po.id} 已无剩余可收数量，无法创建收货任务")

    for rtl in lines_to_create:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)


async def create_for_order(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: Optional[int],
    lines: Sequence[OrderReturnLineIn],
) -> ReceiveTask:
    if not lines:
        raise ValueError("退货行不能为空")

    order_qty_map = await load_order_item_qty_map(session, order_id)
    returned_qty_map = await load_order_returned_qty_map(session, order_id)
    shipped_qty_map = await load_order_shipped_qty_map(session, order_id)

    for rc in lines:
        orig = int(order_qty_map.get(rc.item_id, 0))
        shipped = int(shipped_qty_map.get(rc.item_id, 0))
        already = int(returned_qty_map.get(rc.item_id, 0))
        cap = max(min(orig, shipped) - already, 0)

        if orig <= 0:
            raise ValueError(
                f"订单 {order_id} 中不存在或未记录 item_id={rc.item_id} 的原始数量，无法为该商品创建退货任务"
            )
        if shipped <= 0:
            raise ValueError(
                f"订单 {order_id} 的商品 item_id={rc.item_id} 尚未发货（shipped=0），不能创建退货任务"
            )
        if rc.qty > cap:
            raise ValueError(
                f"订单 {order_id} 的商品 item_id={rc.item_id} 退货数量超出可退上限："
                f"原始数量={orig}，已发货={shipped}，已退={already}，本次请求={rc.qty}，剩余可退={cap}"
            )

    wh_id = warehouse_id or 1

    task = ReceiveTask(
        source_type="ORDER",
        source_id=order_id,
        po_id=None,
        supplier_id=None,
        supplier_name=None,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"return from ORDER-{order_id}",
    )
    session.add(task)
    await session.flush()

    created_lines: list[ReceiveTaskLine] = []
    for rc in lines:
        if rc.qty <= 0:
            continue
        created_lines.append(
            ReceiveTaskLine(
                task_id=task.id,
                po_line_id=None,
                item_id=rc.item_id,
                item_name=rc.item_name,
                item_sku=None,
                category=None,
                spec_text=None,
                base_uom=None,
                purchase_uom=None,
                units_per_case=None,
                batch_code=rc.batch_code,
                production_date=None,
                expiry_date=None,
                expected_qty=rc.qty,
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
        )

    if not created_lines:
        raise ValueError("退货行数量必须大于 0")

    for rtl in created_lines:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)
