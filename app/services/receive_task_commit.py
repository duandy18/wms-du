# app/services/receive_task_commit.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.inbound_service import InboundService
from app.services.order_event_bus import OrderEventBus
from app.services.order_reconcile_service import OrderReconcileService
from app.services.receive_task_loaders import load_item_policy_map, load_po
from app.services.receive_task_query import get_with_lines


NOEXP_BATCH_CODE = "NOEXP"


def _safe_upc(v: Optional[int]) -> int:
    try:
        n = int(v or 1)
    except Exception:
        n = 1
    return n if n > 0 else 1


def _ordered_base(line: PurchaseOrderLine) -> int:
    upc = _safe_upc(getattr(line, "units_per_case", None))
    return int(line.qty_ordered or 0) * upc


def _received_base(line: PurchaseOrderLine) -> int:
    return int(line.qty_received or 0)


def _recalc_po_line_status(line: PurchaseOrderLine) -> None:
    """
    采购行状态推进（✅ base 口径）
    """
    o = _ordered_base(line)
    r = _received_base(line)
    if r <= 0:
        line.status = "CREATED"
    elif r < o:
        line.status = "PARTIAL"
    else:
        line.status = "RECEIVED"


def _recalc_po_header(po: PurchaseOrder, now: datetime) -> None:
    """
    采购单头状态推进（✅ base 口径）
    - all_zero  -> CREATED
    - all_full  -> RECEIVED (+ closed_at)
    - otherwise -> PARTIAL
    并更新 last_received_at / updated_at
    """
    lines = list(po.lines or [])
    all_zero = all(_received_base(line) == 0 for line in lines)
    all_full = all(_received_base(line) >= _ordered_base(line) for line in lines)

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

    # commit 前校验：以 has_shelf_life 为准
    for line in task.lines:
        if not line.scanned_qty or line.scanned_qty == 0:
            continue

        info = policy_map.get(int(line.item_id)) or {}
        has_sl = bool(info.get("has_shelf_life") or False)
        item_name = info.get("name") or line.item_name or f"item_id={line.item_id}"

        if not line.batch_code or not str(line.batch_code).strip():
            if has_sl:
                raise ValueError(f"{item_name} 需要有效期管理，批次不能为空")
            line.batch_code = NOEXP_BATCH_CODE

        if has_sl:
            if line.production_date is None:
                raise ValueError(f"{item_name} 需要有效期管理，必须填写生产日期")
            if line.expiry_date is None:
                sv = info.get("shelf_life_value")
                su = info.get("shelf_life_unit")
                if sv is None or su is None or not str(su).strip():
                    raise ValueError(
                        f"{item_name} 未填写到期日期，且商品未配置保质期参数，无法推算到期日期"
                    )

    now = occurred_at or datetime.now(utc)

    ref = (
        f"RT-{task.id}"
        if task.source_type != "ORDER"
        else f"RMA-{int(task.source_id or 0) or task.id}"
    )

    sub_reason = "RETURN_RECEIPT" if task.source_type == "ORDER" else "PO_RECEIPT"

    po_lines_map: dict[int, PurchaseOrderLine] = {}
    po: Optional[PurchaseOrder] = None
    touched_po_qty = False

    if task.po_id is not None:
        po = await load_po(session, task.po_id)
        for ln in po.lines or []:
            po_lines_map[ln.id] = ln

    receipt: Optional[InboundReceipt] = None
    ref_line_counter = 0
    returned_by_item: dict[int, int] = {}

    for line in task.lines:
        if line.scanned_qty == 0:
            line.committed_qty = 0
            line.status = "COMMITTED"
            continue

        # ✅ scanned_qty 是最小单位（base）
        qty_base = int(line.scanned_qty)
        if qty_base <= 0:
            line.committed_qty = 0
            line.status = "COMMITTED"
            continue

        upc = _safe_upc(getattr(line, "units_per_case", None))
        line.committed_qty = qty_base  # committed_qty 也使用 base
        ref_line_counter += 1

        # 1) 写库存/台账（底座事实）：qty=base
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
            sub_reason=sub_reason,
        )

        line.status = "COMMITTED"

        # 2) 回写 PO 行：qty_received += base
        po_line: Optional[PurchaseOrderLine] = None
        if line.po_line_id is not None and line.po_line_id in po_lines_map:
            po_line = po_lines_map[line.po_line_id]
            po_line.qty_received = int(po_line.qty_received or 0) + qty_base
            _recalc_po_line_status(po_line)
            touched_po_qty = True

        # 3) 收货事实层：第一次遇到实际收货行时创建 header
        if receipt is None:
            supplier_id_val = getattr(task, "supplier_id", None)
            supplier_name_val = getattr(task, "supplier_name", None)

            src_type = str(task.source_type or "PO")
            src_id = (
                int(task.source_id)
                if task.source_id is not None
                else (int(task.po_id) if task.po_id is not None else None)
            )

            receipt = InboundReceipt(
                warehouse_id=int(task.warehouse_id),
                supplier_id=int(supplier_id_val) if supplier_id_val is not None else None,
                supplier_name=str(supplier_name_val) if supplier_name_val else None,
                source_type=src_type,
                source_id=src_id,
                receive_task_id=int(task.id),
                ref=str(ref),
                trace_id=str(trace_id) if trace_id else None,
                status="CONFIRMED",
                remark=str(getattr(task, "remark", "") or ""),
                occurred_at=now,
            )
            session.add(receipt)
            await session.flush()

        # 4) 收货事实层：插 line（补齐快照字段）
        unit_cost: Optional[Decimal] = None
        line_amount: Optional[Decimal] = None

        item_name_snap: Optional[str] = None
        item_sku_snap: Optional[str] = None
        category_snap: Optional[str] = None
        spec_text_snap: Optional[str] = None
        base_uom_snap: Optional[str] = None
        purchase_uom_snap: Optional[str] = None

        po_line_id_val: Optional[int] = None

        if po_line is not None:
            po_line_id_val = int(po_line.id)
            item_name_snap = po_line.item_name
            item_sku_snap = po_line.item_sku
            category_snap = po_line.category
            spec_text_snap = po_line.spec_text
            base_uom_snap = po_line.base_uom
            purchase_uom_snap = po_line.purchase_uom

            if po_line.supply_price is not None:
                unit_cost = Decimal(str(po_line.supply_price))
            if unit_cost is not None:
                line_amount = (Decimal(int(qty_base)) * unit_cost).quantize(Decimal("0.01"))
        else:
            # fallback：task 行快照
            item_name_snap = line.item_name
            item_sku_snap = line.item_sku
            category_snap = line.category
            spec_text_snap = line.spec_text
            base_uom_snap = line.base_uom
            purchase_uom_snap = line.purchase_uom

        receipt_line = InboundReceiptLine(
            receipt_id=int(receipt.id),  # type: ignore[arg-type]
            line_no=int(ref_line_counter),
            po_line_id=po_line_id_val,
            item_id=int(line.item_id),
            item_name=item_name_snap or None,
            item_sku=item_sku_snap or None,
            category=category_snap or None,
            spec_text=spec_text_snap or None,
            base_uom=base_uom_snap or None,
            purchase_uom=purchase_uom_snap or None,
            batch_code=str(line.batch_code),
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            # ✅ qty_received / qty_units 都用 base，允许拆箱/拆件
            qty_received=int(qty_base),
            units_per_case=int(upc),
            qty_units=int(qty_base),
            unit_cost=unit_cost,
            line_amount=line_amount,
            remark=str(line.remark or "") if getattr(line, "remark", None) else None,
        )
        session.add(receipt_line)

        if task.source_type == "ORDER":
            returned_by_item[int(line.item_id)] = returned_by_item.get(int(line.item_id), 0) + qty_base

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
