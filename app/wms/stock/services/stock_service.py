# app/wms/stock/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.stock.services.lot_resolver import LotResolver
from app.wms.stock.services.stock_adjust import adjust_lot_impl
from app.wms.stock.services.stock_ship_service import ship_commit_direct_lot_impl

UTC = timezone.utc


class StockService:
    """
    v2 专业化库存内核（lot-world 终态）。

    终态收口：
    - adjust_lot：lot-only 原语入口，调用方必须先解析 lot_id；
    - lot_resolver：保留给上层服务做合同裁决 + lot_id 解析；
    - 旧 batch_code 合同写入口已退役；公开语义统一为 lot_code。
    """

    def __init__(self, lot_resolver: Optional[LotResolver] = None) -> None:
        self.lot_resolver = lot_resolver or LotResolver()

    async def adjust_lot(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        lot_id: Optional[int],
        delta: int,
        reason: Union[str, MovementType],
        ref: str,
        ref_line: Optional[Union[int, str]] = None,
        occurred_at: Optional[datetime] = None,
        meta: Optional[Dict[str, Any]] = None,
        lot_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        lot-only 原语入口：
        - 不做 lot_code 合同裁决；
        - 调用方必须传入已解析且合法的 lot_id；
        - 保留 ValueError 语义，供服务层/测试按 lot-only 终态处理。
        """
        return await adjust_lot_impl(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_id=lot_id,
            delta=int(delta),
            reason=reason,
            ref=str(ref),
            ref_line=ref_line,
            occurred_at=occurred_at,
            meta=meta,
            lot_code=lot_code,
            production_date=production_date,
            expiry_date=expiry_date,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
        )

    async def ship_commit_direct(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        ref: str,
        lines: list[dict[str, int]],
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await ship_commit_direct_lot_impl(
            session=session,
            warehouse_id=warehouse_id,
            ref=ref,
            lines=lines,
            occurred_at=occurred_at,
            trace_id=trace_id,
            adjust_lot_fn=self.adjust_lot,
        )
