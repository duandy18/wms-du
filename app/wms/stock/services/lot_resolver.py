# app/wms/stock/services/lot_resolver.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full


class LotResolver:
    """
    只负责“lot 决议 + lot 创建/复用”的纯服务：
    - supplier lot: ensure_lot_full
    - internal lot: ensure_internal_lot_singleton（(warehouse,item) 单例）

    当前阶段：
    - REQUIRED lot 身份已切到 (warehouse_id, item_id, production_date)
    - batch_code / lot_code 只作为展示码 / 辅助解析输入
    """

    async def requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        row = await session.execute(
            SA("SELECT expiry_policy FROM items WHERE id=:i LIMIT 1"),
            {"i": int(item_id)},
        )
        v = row.scalar_one_or_none()
        if v is None:
            raise ValueError("item_not_found")
        return str(v or "").upper() == "REQUIRED"

    async def ensure_supplier_lot_id(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        lot_code: str,
        occurred_at: Optional[datetime],
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> int:
        _ = occurred_at
        return await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_code=str(lot_code),
            production_date=production_date,
            expiry_date=expiry_date,
        )

    async def ensure_internal_lot_id(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        occurred_at: Optional[datetime],
        ref: str,
    ) -> int:
        _ = occurred_at
        _ = ref

        return await ensure_internal_lot_singleton(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            source_receipt_id=None,
            source_line_no=None,
        )
