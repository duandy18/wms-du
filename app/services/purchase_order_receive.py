# app/services/purchase_order_receive.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.inbound_service import InboundService
from app.services.purchase_order_queries import get_po_with_lines
from app.services.purchase_order_time import UTC
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl
from app.services.qty_base import remaining_base as _remaining_base_impl


def _ordered_base(line: Any) -> int:
    """
    ✅ ordered_base（base）：统一委托 app/services/qty_base.py
    """
    return _ordered_base_impl(line)


def _received_base(line: Any) -> int:
    """
    ✅ received_base（base）：统一委托 app/services/qty_base.py
    """
    return _received_base_impl(line)


def _remaining_base(line: Any) -> int:
    """
    ✅ remaining_base（base）：统一委托 app/services/qty_base.py
    """
    return _remaining_base_impl(line)


def _recalc_po_line_status(line: PurchaseOrderLine) -> None:
    """
    ✅ 行状态回算（全部 base 口径比较）
    """
    o_base = _ordered_base(line)  # base
    r_base = _received_base(line)  # base

    if r_base <= 0:  # base
        line.status = "CREATED"
    elif r_base < o_base:  # base
        line.status = "PARTIAL"
    elif r_base >= o_base:  # base
        line.status = "RECEIVED"
    else:
        line.status = "CLOSED"


def _recalc_po_header(po: PurchaseOrder, now: datetime) -> None:
    """
    ✅ 头状态回算（全部 base 口径比较）
    """
    lines = list(po.lines or [])
    if not lines:
        po.status = "CREATED"
        po.closed_at = None
        po.last_received_at = now
        return

    all_zero = all(_received_base(ln) == 0 for ln in lines)  # base
    all_full = all(_received_base(ln) >= _ordered_base(ln) for ln in lines)  # base

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


async def receive_po_line(
    inbound_svc: InboundService,
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
) -> PurchaseOrder:
    """
    对某一行执行收货（行级收货）。

    ✅ 口径收敛（重要）：
    - qty 为最小单位（base）
    - PO 行 qty_received 为最小单位（base）
    - ordered_base：优先 qty_ordered_base；旧数据 fallback 才推导（唯一实现见 qty_base.py）
    - remaining_base = ordered_base - qty_received（全部 base 口径）

    关键合同：
    - stock_ledger 存在唯一约束 (reason, ref, ref_line)
      => ref_line 必须在 (reason, ref) 维度全局递增，不能按 item_id 分桶。
    """
    if qty <= 0:  # base
        raise ValueError("收货数量 qty 必须 > 0")
    if line_id is None and line_no is None:
        raise ValueError("receive_po_line 需要提供 line_id 或 line_no 之一")

    po = await get_po_with_lines(session, po_id, for_update=True)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")

    if not po.lines:
        raise ValueError(f"采购单 {po_id} 没有任何行，无法执行行级收货")

    target: Optional[PurchaseOrderLine] = None
    if line_id is not None:
        for line in po.lines:
            if line.id == line_id:
                target = line
                break
    elif line_no is not None:
        for line in po.lines:
            if line.line_no == line_no:
                target = line
                break

    if target is None:
        raise ValueError(
            f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})"
        )

    if target.status in {"RECEIVED", "CLOSED"}:
        raise ValueError(
            f"行已收完或已关闭，无法再收货 (line_id={target.id}, status={target.status})"
        )

    remaining_base = _remaining_base(target)  # base
    if qty > remaining_base:  # base
        raise ValueError(
            f"行收货数量超出剩余数量（base 口径）：ordered_base={_ordered_base(target)}, "
            f"received_base={_received_base(target)}, remaining_base={remaining_base}, try_receive={qty}"
        )

    ref = f"PO-{po.id}"
    reason_val = MovementType.INBOUND.value

    # ✅ ref_line 必须在 (reason, ref) 维度全局递增
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = :reason
            """
        ),
        {"ref": ref, "reason": reason_val},
    )
    max_ref_line = int(row.scalar() or 0)
    next_ref_line = max_ref_line + 1

    # 1) 写库存/台账（qty=最小单位 base）
    await inbound_svc.receive(
        session,
        qty=int(qty),
        ref=ref,
        ref_line=next_ref_line,
        warehouse_id=po.warehouse_id,
        item_id=target.item_id,
        occurred_at=occurred_at or datetime.now(UTC),
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # 2) 回写 PO 行（qty_received=最小单位 base）
    target.qty_received = int(target.qty_received or 0) + int(qty)
    now = datetime.now(UTC)

    _recalc_po_line_status(target)
    _recalc_po_header(po, now)

    await session.flush()
    return po
