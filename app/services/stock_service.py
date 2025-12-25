# app/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service_adjust import adjust_impl
from app.services.stock_service_batches import ensure_batch_dict
from app.services.stock_service_ship import ship_commit_direct_impl

UTC = timezone.utc


class StockService:
    """
    v2 专业化库存内核（槽位维度批次粒度： (item_id, warehouse_id, batch_code)）

    本版本核心增强：
    ------------------------------------------
    1) 正式接入 expiry_resolver（生产日期 + 保质期 → 到期日期）
    2) 所有入库/盘盈自动推算 expiry_date
    3) 批次主档（batches）保证日期属性不被覆盖，但缺失时补齐
    4) 落账前做统一日期校验（exp >= prod）
    5) ledger + stocks 始终得到合法、单一来源的日期
    ------------------------------------------
    """

    async def _ensure_batch_dict(
        self,
        *,
        session: AsyncSession,
        warehouse_id: int,
        item_id: int,
        batch_code: str,
        production_date: Optional[date],
        expiry_date: Optional[date],
        created_at: datetime,
    ) -> None:
        await ensure_batch_dict(
            session=session,
            warehouse_id=warehouse_id,
            item_id=item_id,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            created_at=created_at,
        )

    async def adjust(  # noqa: C901
        self,
        session: AsyncSession,
        item_id: int,
        delta: int,
        reason: Union[str, MovementType],
        ref: str,
        ref_line: Optional[Union[int, str]] = None,
        occurred_at: Optional[datetime] = None,
        meta: Optional[Dict[str, Any]] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        *,
        warehouse_id: int,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await adjust_impl(
            session=session,
            item_id=item_id,
            delta=delta,
            reason=reason,
            ref=ref,
            ref_line=ref_line,
            occurred_at=occurred_at,
            meta=meta,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
            ensure_batch_dict_fn=lambda s, w, i, c, p, e, t: self._ensure_batch_dict(
                session=s,
                warehouse_id=w,
                item_id=i,
                batch_code=c,
                production_date=p,
                expiry_date=e,
                created_at=t,
            ),
        )

    async def ship_commit_direct(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        platform: str,
        shop_id: str,
        ref: str,
        lines: list[dict[str, int]],
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await ship_commit_direct_impl(
            session=session,
            warehouse_id=warehouse_id,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            occurred_at=occurred_at,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
            adjust_fn=self.adjust,
        )
