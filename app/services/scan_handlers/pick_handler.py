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
    batch_code: str | None,
    task_line_id: int | None = None,
    trace_id: str | None = None,  # ★ 新增
) -> dict:
    """
    拣货（Pick）—— v2：以仓库+商品+批次为粒度。

    终态合同：
    - REQUIRED：必须提供 batch_code（由 StockService.adjust -> validate_lot_code_contract 裁决）
    - NONE：batch_code 必须为 null（同上）
    """
    _ = task_line_id

    if qty <= 0:
        raise ValueError("Pick quantity must be positive.")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("拣货操作必须明确 warehouse_id。")

    # 只做轻量归一：把空串/空格变成 None；合同裁决交给 StockService
    bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None

    await StockService().adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=-int(qty),
        reason=MovementType.OUTBOUND,
        ref=ref,
        batch_code=bc_norm,
        trace_id=trace_id,  # ★ 传入
    )
    return {
        "picked": int(qty),
        "batch_code": bc_norm,
        "warehouse_id": int(warehouse_id),
    }
