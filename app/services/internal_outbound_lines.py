# app/services/internal_outbound_lines.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.internal_outbound import InternalOutboundLine

from app.services.internal_outbound_query import get_with_lines


async def upsert_line(
    session: AsyncSession,
    *,
    doc_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str] = None,
    uom: Optional[str] = None,
    note: Optional[str] = None,
):
    """
    对内部出库单新增或累加一行：
    - 仅允许在 DRAFT 状态下修改；
    - 若同一 doc 下已存在 (item_id, batch_code) 则累加 requested_qty；
    - 否则新建一行，line_no = 当前最大行号 + 1；
    - qty 可为正数（新增）或负数（减少），但最终 requested_qty 不得小于 0。
    """
    if qty == 0:
        return await get_with_lines(session, doc_id)

    doc = await get_with_lines(session, doc_id, for_update=True)
    if doc.status != "DRAFT":
        raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能修改行")

    norm_code = batch_code.strip() if batch_code is not None else None

    target: Optional[InternalOutboundLine] = None
    for ln in doc.lines or []:
        if ln.item_id == item_id and (ln.batch_code or "") == (norm_code or ""):
            target = ln
            break

    if target is None:
        next_line_no = 1
        if doc.lines:
            next_line_no = max(ln.line_no for ln in doc.lines) + 1

        target = InternalOutboundLine(
            doc_id=doc.id,
            line_no=next_line_no,
            item_id=item_id,
            batch_code=norm_code,
            requested_qty=int(qty),
            confirmed_qty=None,
            uom=uom,
            note=note,
        )
        if target.requested_qty < 0:
            raise ValueError(
                f"内部出库行数量不能为负：item_id={item_id}, batch_code={norm_code}, after={target.requested_qty}"
            )
        session.add(target)
    else:
        target.requested_qty += int(qty)
        if target.requested_qty < 0:
            raise ValueError(
                f"内部出库行数量不能为负：item_id={item_id}, batch_code={norm_code}, after={target.requested_qty}"
            )

        if norm_code is not None and not target.batch_code:
            target.batch_code = norm_code
        if note is not None:
            target.note = note
        if uom is not None:
            target.uom = uom

    await session.flush()
    return await get_with_lines(session, doc.id)
