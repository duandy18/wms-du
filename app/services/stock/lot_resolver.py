# app/services/stock/lot_resolver.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock.lots import ensure_internal_lot_singleton, ensure_lot_full


def _norm_lot_code_key(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s.upper()


class LotResolver:
    """
    只负责“lot 决议 + lot 创建/复用”的纯服务：
    - supplier lot: ensure_lot_full（partial unique index 的 ON CONFLICT 必须带 WHERE）
    - internal lot: ensure_internal_lot_singleton（(warehouse,item) 单例）
    - 可用量估算：仅用于错误提示/诊断（不参与扣减决策）
    """

    async def requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        row = await session.execute(
            SA("SELECT expiry_policy FROM items WHERE id=:i LIMIT 1"),
            {"i": int(item_id)},
        )
        v = row.scalar_one_or_none()
        if v is None:
            # unknown item 必须先拦住，不能被 NONE/REQUIRED 合同判断遮蔽
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
    ) -> int:
        _ = occurred_at
        # Phase 2：Lot upsert 收口到 app/services/stock/lots.py（ensure_lot_full）
        return await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_code=str(lot_code),
            production_date=None,
            expiry_date=None,
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

        # INTERNAL 单例必须走 partial unique index 语义：
        # 不允许再出现 ON CONFLICT (warehouse_id,item_id) 这种旧世界写法。
        return await ensure_internal_lot_singleton(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            source_receipt_id=None,
            source_line_no=None,
        )

    async def load_on_hand_qty(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        """
        只用于错误提示/诊断的“可用量”估算：
        - batch_code 非空：按 lot_code_key（防漂移）聚合 SUPPLIER lot 的余额
        - batch_code 为空：聚合该 item 在该仓的总余额
        """
        if batch_code is None:
            row = (
                await session.execute(
                    SA(
                        """
                        SELECT COALESCE(SUM(s.qty), 0) AS qty
                          FROM stocks_lot s
                         WHERE s.warehouse_id = :w
                           AND s.item_id      = :i
                        """
                    ),
                    {"w": int(warehouse_id), "i": int(item_id)},
                )
            ).first()
        else:
            k = _norm_lot_code_key(batch_code) or ""
            row = (
                await session.execute(
                    SA(
                        """
                        SELECT COALESCE(SUM(s.qty), 0) AS qty
                          FROM stocks_lot s
                          JOIN lots lo ON lo.id = s.lot_id
                         WHERE s.warehouse_id = :w
                           AND s.item_id      = :i
                           AND lo.lot_code_source = 'SUPPLIER'
                           AND lo.lot_code_key = :k
                        """
                    ),
                    {"w": int(warehouse_id), "i": int(item_id), "k": str(k)},
                )
            ).first()

        if not row:
            return 0
        try:
            return int(row[0] or 0)
        except Exception:
            return 0
