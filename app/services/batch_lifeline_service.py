# app/services/batch_lifeline_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code

_NULL_BATCH_KEY = "__NULL_BATCH__"


class BatchLifelineService:
    """
    批次生命周期：
    inbound → adjust → pick → ship → count → ledger → stocks/snapshot

    Phase 4E（真收口）：
    - 主读：stocks_lot（lot-world，展示码 lots.lot_code 对齐 batch_code）
    - 禁止读取 legacy stocks（不做 shadow fallback，不允许双余额源）
    """

    @staticmethod
    async def load_lifeline(
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> Dict[str, Any]:
        norm_bc = normalize_optional_batch_code(batch_code)
        batch_code_key = _NULL_BATCH_KEY if norm_bc is None else norm_bc

        base: Dict[str, Any] = {
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "batch_code": norm_bc,
            "batch_code_key": str(batch_code_key),
        }

        # ledger timeline（按 batch_code_key 维度对齐 NULL 语义）
        rs = await session.execute(
            text(
                """
                SELECT id, occurred_at, reason, delta, after_qty,
                       trace_id, ref, batch_code, batch_code_key
                FROM stock_ledger
                WHERE warehouse_id=:w AND item_id=:i AND batch_code_key=:ck
                ORDER BY occurred_at ASC, id ASC
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "ck": str(batch_code_key)},
        )
        base["ledger"] = [dict(r) for r in rs.mappings().all()]

        # current stock：主读 stocks_lot（lot_code==batch_code）
        rs = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.qty), 0) AS qty, COUNT(*) AS n
                FROM stocks_lot s
                LEFT JOIN lots lo ON lo.id = s.lot_id
                WHERE s.warehouse_id=:w
                  AND s.item_id=:i
                  AND lo.lot_code IS NOT DISTINCT FROM :c
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": norm_bc},
        )
        r = rs.mappings().first()
        if r and int(r["n"] or 0) > 0:
            base["current_stock"] = int(r["qty"] or 0)
        else:
            # Phase 4E：不允许 fallback 到 legacy stocks；缺失即视为 0
            base["current_stock"] = 0

        return base
