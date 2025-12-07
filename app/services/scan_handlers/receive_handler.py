# app/services/scan_handlers/receive_handler.py
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item


async def handle_receive(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref: str,
    batch_code: str,
    production_date: date | None = None,
    expiry_date: date | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    入库（Receive）—— v2：以 仓库 + 商品 + 批次 为粒度。

    日期策略：
    - 若显式提供 expiry_date → 直接使用；
    - 否则在有 production_date 且 Item 配置了保质期时自动推算 expiry_date；
    - 若两者都缺失 → 直接报错（扫描端必须显式录入）。
    """
    if qty <= 0:
        raise ValueError("Receive quantity must be positive.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("入库操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("入库操作必须明确 warehouse_id。")

    # 要么给了到期日，要么至少给生产日；否则直接视为输入不完整
    if production_date is None and expiry_date is None:
        raise ValueError("入库操作必须提供 production_date 或 expiry_date（至少其一）。")

    # 结合 Item 保质期配置推算最终日期（若可能）
    production_date, expiry_date = await resolve_batch_dates_for_item(
        session,
        item_id=item_id,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    await StockService().adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=int(qty),
        reason=MovementType.INBOUND,
        ref=ref,
        batch_code=str(batch_code).strip(),
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
    )
    return {
        "qty": int(qty),
        "batch_code": str(batch_code),
        "warehouse_id": int(warehouse_id),
    }
