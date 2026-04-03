from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.stock.services.stock_service import StockService


async def apply_inbound_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
    qty: int,
    ref: str,
    ref_line: int,
    occurred_at: datetime | None,
    batch_code: str | None,
    trace_id: str,
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
) -> dict[str, Any]:
    """
    第一阶段 repo 仍临时包裹既有 StockService.adjust_lot。
    这样 atomic service 不直接依赖旧 service 细节。
    """
    stock_svc = StockService()

    return await stock_svc.adjust_lot(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=int(qty),
        reason=MovementType.INBOUND,
        ref=str(ref),
        ref_line=int(ref_line),
        occurred_at=occurred_at,
        batch_code=batch_code,
        meta={
            "sub_reason": "ATOMIC_INBOUND",
            "source_type": source_type,
            "source_biz_type": source_biz_type,
            "source_ref": source_ref,
            "remark": remark,
        },
        production_date=None,
        expiry_date=None,
        trace_id=trace_id,
        shadow_write_stocks=False,
    )


__all__ = ["apply_inbound_stock"]
