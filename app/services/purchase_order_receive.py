# app/services/purchase_order_receive.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.purchase_order_queries import get_po_with_lines
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl
from app.services.qty_base import remaining_base as _remaining_base_impl


def _ordered_base(line: Any) -> int:
    return _ordered_base_impl(line)


def _received_base(line: Any) -> int:
    return _received_base_impl(line)


def _remaining_base(line: Any) -> int:
    return _remaining_base_impl(line)


async def _get_latest_po_draft_receipt(session: AsyncSession, *, po_id: int) -> Optional[InboundReceipt]:
    stmt = (
        select(InboundReceipt)
        .where(InboundReceipt.source_type == "PO")
        .where(InboundReceipt.source_id == int(po_id))
        .where(InboundReceipt.status == "DRAFT")
        .order_by(InboundReceipt.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _get_po_draft_receipt(session: AsyncSession, *, po_id: int) -> Optional[InboundReceipt]:
    return await _get_latest_po_draft_receipt(session, po_id=int(po_id))


async def _create_po_draft_receipt(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    """
    显式创建 DRAFT receipt（只创建，不复用）。
    注意：DB 有 partial unique（PO + DRAFT），并发下可能冲突。
    """
    ts = int(occurred_at.timestamp() * 1000)
    ref = f"DRFT-PO-{po.id}-{ts}"

    r = InboundReceipt(
        warehouse_id=int(po.warehouse_id),
        supplier_id=getattr(po, "supplier_id", None),
        supplier_name=getattr(po, "supplier_name", None),
        source_type="PO",
        source_id=int(po.id),
        ref=ref,
        trace_id=None,
        status="DRAFT",
        remark="explicit draft (Phase5)",
        occurred_at=occurred_at,
    )
    session.add(r)
    await session.flush()
    return r


async def get_or_create_po_draft_receipt_explicit(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    """
    显式入口（给 POST draft 用）：
    - 先查现有 DRAFT，有则复用
    - 没有才创建
    - 并发下若触发 partial unique：自动 rollback 后再查一次（幂等）
    """
    draft = await _get_po_draft_receipt(session, po_id=int(po.id))
    if draft is not None:
        return draft

    try:
        return await _create_po_draft_receipt(session, po=po, occurred_at=occurred_at)
    except IntegrityError:
        # 并发下另一个事务已经创建了 DRAFT：回滚本次 flush 冲突，再查一次返回
        await session.rollback()
        draft2 = await _get_po_draft_receipt(session, po_id=int(po.id))
        if draft2 is not None:
            return draft2
        raise


async def _next_receipt_line_no(session: AsyncSession, *, receipt_id: int) -> int:
    """
    在 async 环境中禁止访问 receipt.lines（可能触发 lazyload -> MissingGreenlet）。
    这里用 SQL 直接取 MAX(line_no)+1，稳定且无懒加载风险。
    """
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(line_no), 0) AS mx
              FROM inbound_receipt_lines
             WHERE receipt_id = :rid
            """
        ),
        {"rid": int(receipt_id)},
    )
    mx = int(row.scalar() or 0)
    return mx + 1


def _build_batch_code(*, po_id: int, po_line_no: int, production_date: Optional[date]) -> str:
    """
    Phase5：录入阶段必须给 batch_code（DB NOT NULL）。
    - 若提供 production_date：用可解释的 deterministic batch_code
    - 若未提供：先落 NOEXP（后续在 Receipt 页面补齐/修正）
    """
    if production_date is None:
        return "NOEXP"
    return f"BATCH-PO{po_id}-L{po_line_no}-{production_date.isoformat()}"


async def receive_po_line(
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    barcode: Optional[str] = None,
) -> PurchaseOrder:
    """
    Phase5：对某一行执行“收货录入”（行级）。
    - ✅ 只写 Receipt(DRAFT) 事实（InboundReceipt / InboundReceiptLine）
    - ❌ 不写 stock_ledger / stocks / snapshot（库存动作只能由 Receipt(CONFIRMED) 触发）
    - qty 为最小单位（base）

    关键收敛：不再隐式创建 DRAFT receipt
    - 必须先通过显式接口创建/复用 DRAFT receipt
    """
    if qty <= 0:
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
        raise ValueError(f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})")

    if target.status in {"RECEIVED", "CLOSED"}:
        raise ValueError(f"行已收完或已关闭，无法再收货 (line_id={target.id}, status={target.status})")

    remaining_base = int(_remaining_base(target) or 0)
    if qty > remaining_base:
        raise ValueError(
            f"行收货数量超出剩余数量（base 口径）：ordered_base={_ordered_base(target)}, "
            f"received_base={_received_base(target)}, remaining_base={remaining_base}, try_receive={qty}"
        )


    # 1) 必须已有 DRAFT Receipt（显式创建）
    draft = await _get_po_draft_receipt(session, po_id=int(po.id))
    if draft is None:
        raise ValueError(f"请先开始收货：未找到 PO 的 DRAFT 收货单 (po_id={po_id})")

    # 2) 生成 line_no（receipt 内递增）——使用 SQL，避免 draft.lines 懒加载
    next_line_no = await _next_receipt_line_no(session, receipt_id=int(draft.id))

    # 3) 写入 ReceiptLine
    units_per_case = int(getattr(target, "units_per_case", 1) or 1)
    po_line_no_val = int(getattr(target, "line_no", 0) or 0)
    batch_code = _build_batch_code(
        po_id=int(po.id),
        po_line_no=po_line_no_val,
        production_date=production_date,
    )

    rl = InboundReceiptLine(
        receipt_id=int(draft.id),
        line_no=int(next_line_no),
        po_line_id=int(getattr(target, "id")),
        item_id=int(getattr(target, "item_id")),
        item_name=getattr(target, "item_name", None),
        item_sku=getattr(target, "item_sku", None),
        category=getattr(target, "category", None),
        spec_text=getattr(target, "spec_text", None),
        base_uom=getattr(target, "base_uom", None),
        purchase_uom=getattr(target, "purchase_uom", None),
        barcode=(str(barcode).strip() if barcode is not None and str(barcode).strip() else None),
        batch_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
        qty_received=int(qty),
        units_per_case=int(units_per_case),
        qty_units=int(qty),  # 继续沿用 base=units 的既有口径
        unit_cost=None,
        line_amount=None,
        remark=None,
    )
    session.add(rl)
    await session.flush()

    return po
