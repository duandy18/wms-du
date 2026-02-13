# app/services/rma_service.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.warehouse import WarehouseCode
from app.services.stock_service import StockService


class RMAService:
    """
    退货三段式（Phase 3：所有库存变化必须走 StockService.adjust）：
      1) RETURN_IN → RETURNS（净增退货池）
      2) RECLASSIFY RETURNS→MAIN（净零迁移，可售量+）
      3) RETURN_SCRAP@RETURNS（净减，报废）

    ✅ Phase 3 合同：
    - 禁止在业务服务里直接 write_ledger / 直接改 stocks
    - 一切库存变化统一通过 StockService.adjust（内部完成：幂等 + 写台账 + 改库存）
    """

    async def return_in(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        batch_code: str,
        qty: int,
        rma_ref: str,
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh = await self._wh_id(session, WarehouseCode.RETURNS)

        # 入退货池：RETURNS +qty
        await StockService.adjust(
            session=session,
            warehouse_id=int(wh),
            item_id=int(item_id),
            batch_code=str(batch_code),
            delta=int(qty),
            reason="RETURN_IN",
            ref=str(rma_ref),
            ref_line=1,
            occurred_at=occurred_at,
            trace_id=trace_id,
            meta={"sub_reason": "RMA_RETURN_IN"},
        )

    async def reclassify_to_main(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        batch_code: str,
        qty: int,
        rma_ref: str,
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh_ret = await self._wh_id(session, WarehouseCode.RETURNS)
        wh_main = await self._wh_id(session, WarehouseCode.MAIN)

        # RETURNS 减（会在 StockService.adjust 内做不足校验）
        await StockService.adjust(
            session=session,
            warehouse_id=int(wh_ret),
            item_id=int(item_id),
            batch_code=str(batch_code),
            delta=-int(qty),
            reason="RETURN_RECLASSIFY",
            ref=str(rma_ref),
            ref_line=2,
            occurred_at=occurred_at,
            trace_id=trace_id,
            meta={"sub_reason": "RMA_RECLASSIFY_OUT"},
        )

        # MAIN 加
        await StockService.adjust(
            session=session,
            warehouse_id=int(wh_main),
            item_id=int(item_id),
            batch_code=str(batch_code),
            delta=int(qty),
            reason="RETURN_RECLASSIFY",
            ref=str(rma_ref),
            ref_line=3,
            occurred_at=occurred_at,
            trace_id=trace_id,
            meta={"sub_reason": "RMA_RECLASSIFY_IN"},
        )

    async def scrap_in_returns(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        batch_code: str,
        qty: int,
        rma_ref: str,
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh = await self._wh_id(session, WarehouseCode.RETURNS)

        # RETURNS 报废：RETURNS -qty（不足校验由 StockService.adjust 负责）
        await StockService.adjust(
            session=session,
            warehouse_id=int(wh),
            item_id=int(item_id),
            batch_code=str(batch_code),
            delta=-int(qty),
            reason="RETURN_SCRAP",
            ref=str(rma_ref),
            ref_line=4,
            occurred_at=occurred_at,
            trace_id=trace_id,
            meta={"sub_reason": "RMA_SCRAP"},
        )

    # helpers
    @staticmethod
    async def _wh_id(session: AsyncSession, code: str) -> int:
        r = await session.execute(
            sa.text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": code}
        )
        wid = r.scalar_one_or_none()
        if wid is None:
            ins = await session.execute(
                sa.text(
                    "INSERT INTO warehouses(name) VALUES(:n) ON CONFLICT (name) DO NOTHING RETURNING id"
                ),
                {"n": code},
            )
            wid = ins.scalar()
            if wid is None:
                r2 = await session.execute(
                    sa.text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": code}
                )
                wid = r2.scalar_one()
        return int(wid)
