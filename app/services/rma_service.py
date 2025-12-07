# app/services/rma_service.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.warehouse import WarehouseCode
from app.services.ledger_writer import write_ledger


class RMAService:
    """
    退货三段式：
      1) RETURN_IN → RETURNS（净增退货池）
      2) RECLASSIFY RETURNS→MAIN（净零迁移，可售量+）
      3) RETURN_SCRAP@RETURNS（净减，报废）
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
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh = await self._wh_id(session, WarehouseCode.RETURNS)
        stk = await self._lock_stock(session, wh, item_id, batch_code)
        if stk is None:
            stk = Stock(warehouse_id=wh, item_id=item_id, batch_code=batch_code, qty=0)
            session.add(stk)
        stk.qty += qty
        await write_ledger(
            session,
            warehouse_id=wh,
            item_id=item_id,
            batch_code=batch_code,
            reason="RETURN_IN",
            delta=qty,
            after_qty=stk.qty,
            ref=rma_ref,
            ref_line=1,
            occurred_at=occurred_at,
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
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh_ret = await self._wh_id(session, WarehouseCode.RETURNS)
        wh_main = await self._wh_id(session, WarehouseCode.MAIN)

        # RETURNS 减
        stk_ret = await self._lock_stock(session, wh_ret, item_id, batch_code)
        if stk_ret is None or stk_ret.qty < qty:
            raise ValueError("RETURNS pool insufficient")
        stk_ret.qty -= qty
        await write_ledger(
            session,
            warehouse_id=wh_ret,
            item_id=item_id,
            batch_code=batch_code,
            reason="RETURN_RECLASSIFY",
            delta=-qty,
            after_qty=stk_ret.qty,
            ref=rma_ref,
            ref_line=2,
            occurred_at=occurred_at,
        )

        # MAIN 加
        stk_main = await self._lock_stock(session, wh_main, item_id, batch_code)
        if stk_main is None:
            stk_main = Stock(warehouse_id=wh_main, item_id=item_id, batch_code=batch_code, qty=0)
            session.add(stk_main)
        stk_main.qty += qty
        await write_ledger(
            session,
            warehouse_id=wh_main,
            item_id=item_id,
            batch_code=batch_code,
            reason="RETURN_RECLASSIFY",
            delta=qty,
            after_qty=stk_main.qty,
            ref=rma_ref,
            ref_line=3,
            occurred_at=occurred_at,
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
    ) -> None:
        occurred_at = occurred_at or datetime.now(UTC)
        wh = await self._wh_id(session, WarehouseCode.RETURNS)
        stk = await self._lock_stock(session, wh, item_id, batch_code)
        if stk is None or stk.qty < qty:
            raise ValueError("RETURNS pool insufficient to scrap")
        stk.qty -= qty
        await write_ledger(
            session,
            warehouse_id=wh,
            item_id=item_id,
            batch_code=batch_code,
            reason="RETURN_SCRAP",
            delta=-qty,
            after_qty=stk.qty,
            ref=rma_ref,
            ref_line=4,
            occurred_at=occurred_at,
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

    @staticmethod
    async def _lock_stock(session: AsyncSession, wh: int, item: int, code: str) -> Stock | None:
        row = await session.execute(
            sa.select(Stock)
            .where(Stock.warehouse_id == wh, Stock.item_id == item, Stock.batch_code == code)
            .with_for_update()
        )
        return row.scalar_one_or_none()
