from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.contracts.item_policy import ItemPolicy
from app.wms.stock.services.lot_service import resolve_or_create_lot


def infer_lot_code_source_from_policy(item_policy: ItemPolicy) -> str:
    """
    当前中心任务收口：

    - REQUIRED 商品：走 SUPPLIER lot 路径，由 production_date 决定 lot 身份
    - 其他商品：统一走 INTERNAL singleton
    """
    if str(item_policy.expiry_policy or "").upper() == "REQUIRED":
        return "SUPPLIER"
    return "INTERNAL"


async def resolve_inbound_lot(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_policy: ItemPolicy,
    lot_code: str | None,
    production_date: date | None,
    expiry_date: date | None,
) -> int:
    lot_code_source = infer_lot_code_source_from_policy(item_policy)

    source_receipt_id = None
    source_line_no = None

    if lot_code_source != "SUPPLIER":
        lot_code = None
        production_date = None
        expiry_date = None

    return await resolve_or_create_lot(
        db=session,
        warehouse_id=int(warehouse_id),
        item_policy=item_policy,
        lot_code_source=lot_code_source,
        lot_code=lot_code,
        production_date=production_date,
        expiry_date=expiry_date,
        source_receipt_id=source_receipt_id,
        source_line_no=source_line_no,
    )


__all__ = [
    "infer_lot_code_source_from_policy",
    "resolve_inbound_lot",
]
