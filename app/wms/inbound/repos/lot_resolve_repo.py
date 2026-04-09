from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.contracts.item_policy import ItemPolicy
from app.wms.stock.services.lot_service import resolve_or_create_lot


def infer_lot_code_source_from_policy(item_policy: ItemPolicy) -> str:
    """
    原子入库第一阶段最小规则：
    - 商品 lot_source_policy = SUPPLIER_ONLY 时，用 SUPPLIER
    - 其他默认 INTERNAL
    """
    if item_policy.lot_source_policy == "SUPPLIER_ONLY":
        return "SUPPLIER"
    return "INTERNAL"


async def resolve_inbound_lot(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_policy: ItemPolicy,
    lot_code: str | None,
) -> int:
    lot_code_source = infer_lot_code_source_from_policy(item_policy)

    source_receipt_id = None
    source_line_no = None

    if lot_code_source != "SUPPLIER":
        lot_code = None

    return await resolve_or_create_lot(
        db=session,
        warehouse_id=int(warehouse_id),
        item_policy=item_policy,
        lot_code_source=lot_code_source,
        lot_code=lot_code,
        source_receipt_id=source_receipt_id,
        source_line_no=source_line_no,
    )


__all__ = [
    "infer_lot_code_source_from_policy",
    "resolve_inbound_lot",
]
