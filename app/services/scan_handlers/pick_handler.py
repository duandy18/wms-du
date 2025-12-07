# app/services/scan_handlers/pick_handler.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


async def handle_pick(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref: str,
    batch_code: str,
    task_line_id: int | None = None,
    trace_id: str | None = None,  # ★ 新增
) -> dict:
    """
    拣货（Pick）—— v2：以仓库+商品+批次为粒度。
    """
    if qty <= 0:
        raise ValueError("Pick quantity must be positive.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("拣货操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("拣货操作必须明确 warehouse_id。")

    await StockService().adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=-int(qty),
        reason=MovementType.OUTBOUND,
        ref=ref,
        batch_code=str(batch_code).strip(),
        trace_id=trace_id,  # ★ 传入
    )
    return {
        "picked": int(qty),
        "batch_code": str(batch_code),
        "warehouse_id": int(warehouse_id),
    }
