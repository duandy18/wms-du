from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)
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
    lot_code: str | None,
    production_date: date | None,
    expiry_date: date | None,
    event_id: int | None = None,
    trace_id: str,
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
) -> dict[str, Any]:
    """
    第一阶段 repo 仍临时包裹既有 StockService.adjust_lot。
    这样 inbound 调用方不直接依赖旧 service 细节。

    当前中心任务：
    - 新主链：业务事件 event_id 与技术链路 trace_id 一起向下传
    - 旧兼容路径：允许 event_id 为空，先保证不被签名收紧打断
    - occurred_at 必须使用外部业务发生时间，不允许在此层被覆盖
    - production_date / expiry_date 必须继续向下传，
      让 lot snapshot 与 RECEIPT ledger snapshot 使用同一决策输入
    """
    await ensure_warehouse_not_frozen(
        session,
        warehouse_id=int(warehouse_id),
    )

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
        lot_code=lot_code,
        meta={
            "sub_reason": "ATOMIC_INBOUND",
            "event_id": int(event_id) if event_id is not None else None,
            "source_type": source_type,
            "source_biz_type": source_biz_type,
            "source_ref": source_ref,
            "remark": remark,
        },
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
    )


__all__ = ["apply_inbound_stock"]
