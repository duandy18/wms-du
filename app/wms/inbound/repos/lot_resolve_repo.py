from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.wms.stock.services.lot_service import resolve_or_create_lot


def infer_lot_code_source_from_item(item: Item) -> str:
    """
    原子入库第一阶段最小规则：
    - 有明确 supplier lot 语义时用 SUPPLIER
    - 其他默认 INTERNAL
    """
    v = getattr(item, "lot_source_policy", None)
    s = str(v or "").strip().upper()
    if s == "SUPPLIER":
        return "SUPPLIER"
    return "INTERNAL"


async def resolve_inbound_lot(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item: Item,
    lot_code: str | None,
) -> int:
    lot_code_source = infer_lot_code_source_from_item(item)

    source_receipt_id = None
    source_line_no = None

    if lot_code_source != "SUPPLIER":
        lot_code = None

    return await resolve_or_create_lot(
        db=session,
        warehouse_id=int(warehouse_id),
        item=item,
        lot_code_source=lot_code_source,
        lot_code=lot_code,
        source_receipt_id=source_receipt_id,
        source_line_no=source_line_no,
    )


__all__ = [
    "infer_lot_code_source_from_item",
    "resolve_inbound_lot",
]
