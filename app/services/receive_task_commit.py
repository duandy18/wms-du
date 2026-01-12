# app/services/receive_task_commit.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.inbound_service import InboundService
from app.services.order_event_bus import OrderEventBus
from app.services.order_reconcile_service import OrderReconcileService
from app.services.receive_task_loaders import load_item_policy_map, load_po
from app.services.receive_task_query import get_with_lines


NOEXP_BATCH_CODE = "NOEXP"


def _recalc_po_line_status(line: PurchaseOrderLine) -> None:
    """
    采购行状态推进（与 purchase_order_receive.py 保持同口径）
    """
    if int(line.qty_received or 0) <= 0:
        line.status = "CREATED"
    elif int(line.qty_received or 0) < int(line.qty_ordered or 0):
        line.status = "PARTIAL"
    elif int(line.qty_received or 0) == int(line.qty_ordered or 0):
        line.status = "RECEIVED"
    else:
        line.status = "CLOSED"


def _recalc_po_header(po: PurchaseOrder, now: datetime) -> None:
    """
    采购单头状态推进（与 purchase_order_receive.py 保持同口径）
    - all_zero  -> CREATED
    - all_full  -> RECEIVED (+ closed_at)
    - otherwise -> PARTIAL
    并更新 last_received_at / updated_at
    """
    lines = list(po.lines or [])
    all_zero = all(int(line.qty_received or 0) == 0 for line in lines)
    all_full = all(int(line.qty_received or 0) >= int(line.qty_ordered or 0) for line in lines)

    if all_zero:
        po.status = "CREATED"
        po.closed_at = None
    elif all_full:
        po.status = "RECEIVED"
        po.closed_at = now
    else:
        po.status = "PARTIAL"
        po.closed_at = None

    po.last_received_at = now
    po.updated_at = now


async def commit(
    session: AsyncSession,
    *,
    inbound_svc: InboundService,
    task_id: int,
    trace_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    utc,
):
    task = await get_with_lines(session, task_id, for_update=True)
    if task.status != "DRAFT":
        raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能重复 commit")
    if not task.lines:
        raise ValueError(f"任务 {task.id} 没有任何行，不能 commit")

    item_ids = sorted({int(line.item_id) for line in task.lines if line.item_id})
    policy_map = await load_item_policy_map(session, item_ids)

    # ★ commit 前校验：以 has_shelf_life 为准
    for line in task.lines:
        if not line.scanned_qty or line.scanned_qty == 0:
            continue

        info = policy_map.get(int(line.item_id)) or {}
        has_sl = bool(info.get("has_shelf_life") or False)
        item_name = info.get("name") or line.item_name or f"item_id={line.item_id}"

        # batch_code：两种都要求（无有效期可自动 NOEXP）
        if not line.batch_code or not str(line.batch_code).strip():
            if has_sl:
                raise ValueError(f"{item_name} 需要有效期管理，批次不能为空")
            line.batch_code = NOEXP_BATCH_CODE

        if has_sl:
            # 必须生产日期
            if line.production_date is None:
                raise ValueError(f"{item_name} 需要有效期管理，必须填写生产日期")
            # expiry 可缺省，但缺省时必须有参数可推算
            if line.expiry_date is None:
                sv = info.get("shelf_life_value")
                su = info.get("shelf_life_unit")
                if sv is None or su is None or not str(su).strip():
                    raise ValueError(
                        f"{item_name} 未填写到期日期，且商品未配置保质期参数，无法推算到期日期"
                    )
        else:
            pass

    now = occurred_at or datetime.now(utc)

    ref = f"RT-{task.id}" if task.source_type != "ORDER" else f"RMA-{int(task.source_id or 0) or task.id}"

    # ✅ 合同化：sub_reason（业务细分）
    # - PO/非订单来源：采购收货入库
    # - ORDER 来源：客户退货回仓入库
    sub_reason = "RETURN_RECEIPT" if task.source_type == "ORDER" else "PO_RECEIPT"

    po_lines_map: dict[int, PurchaseOrderLine] = {}
    po: Optional[PurchaseOrder] = None
    touched_po_qty = False

    if task.po_id is not None:
        po = await load_po(session, task.po_id)
        for line in po.lines or []:
            po_lines_map[line.id] = line

    ref_line_counter = 0
    returned_by_item: dict[int, int] = {}

    for line in task.lines:
        if line.scanned_qty == 0:
            line.committed_qty = 0
            line.status = "COMMITTED"
            continue

        qty_purchase = int(line.scanned_qty)
        factor = int(line.units_per_case or 1)
        if factor <= 0:
            factor = 1
        qty_base = qty_purchase * factor

        line.committed_qty = qty_purchase
        ref_line_counter += 1

        await inbound_svc.receive(
            session=session,
            qty=qty_base,
            ref=ref,
            ref_line=ref_line_counter,
            warehouse_id=task.warehouse_id,
            item_id=line.item_id,
            batch_code=line.batch_code,
            occurred_at=now,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            trace_id=trace_id,
            sub_reason=sub_reason,  # ✅ 关键：把业务细分写进台账
        )

        line.status = "COMMITTED"

        if line.po_line_id is not None and line.po_line_id in po_lines_map:
            po_line = po_lines_map[line.po_line_id]
            po_line.qty_received += qty_purchase
            _recalc_po_line_status(po_line)
            touched_po_qty = True

        if task.source_type == "ORDER":
            returned_by_item[line.item_id] = returned_by_item.get(line.item_id, 0) + qty_purchase

    # ✅ 补齐：如果发生了 PO 行回写，则推进 PO 单头状态/时间
    if po is not None and touched_po_qty:
        _recalc_po_header(po, now)

    task.status = "COMMITTED"
    await session.flush()

    if task.source_type == "ORDER" and task.source_id:
        order_id = int(task.source_id)
        try:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT platform, shop_id, ext_order_no
                          FROM orders
                         WHERE id = :oid
                         LIMIT 1
                        """
                    ),
                    {"oid": order_id},
                )
            ).first()
            if row:
                plat, shop_id, ext_no = row
                order_ref = f"ORD:{str(plat).upper()}:{shop_id}:{ext_no}"
            else:
                order_ref = ref

            await OrderEventBus.order_returned(
                session,
                ref=order_ref,
                order_id=order_id,
                warehouse_id=task.warehouse_id,
                lines=[{"item_id": iid, "qty": qty} for iid, qty in returned_by_item.items()],
                trace_id=trace_id,
            )

            recon = OrderReconcileService(session)
            result = await recon.reconcile_order(order_id)
            await recon.apply_counters(order_id)

            full_returned = all(line_result.remaining_refundable == 0 for line_result in result.lines)
            new_status = "RETURNED" if full_returned else "PARTIALLY_RETURNED"

            await session.execute(
                text(
                    """
                    UPDATE orders
                       SET status = :st,
                           updated_at = NOW()
                     WHERE id = :oid
                    """
                ),
                {"st": new_status, "oid": order_id},
            )

        except Exception:
            pass

    return await get_with_lines(session, task.id)
