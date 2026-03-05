# app/services/batch_lifeline_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import normalize_optional_lot_code


class BatchLifelineService:
    """
    批次生命周期（展示码维度）：

    inbound → adjust → pick → ship → count → ledger → stocks/snapshot

    Phase M-5（终态要点）：
    - 主读：stocks_lot（lot-world）
    - batch_code 仅为展示/输入标签：实际值为 lots.lot_code（可能为 NULL）
    - 禁止 batch_code_key / __NULL_BATCH__ sentinel（避免语义回潮）
    """

    @staticmethod
    async def load_lifeline(
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> Dict[str, Any]:
        norm_bc = normalize_optional_lot_code(batch_code)

        base: Dict[str, Any] = {
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "batch_code": norm_bc,
        }

        # ledger timeline（按展示码 lots.lot_code 对齐 NULL 语义；不使用 batch_code_key）
        rs = await session.execute(
            text(
                """
                SELECT
                  l.id,
                  l.occurred_at,
                  l.reason,
                  l.delta,
                  l.after_qty,
                  l.trace_id,
                  l.ref,
                  l.ref_line,
                  l.lot_id,
                  lo.lot_code AS batch_code
                FROM stock_ledger l
                LEFT JOIN lots lo ON lo.id = l.lot_id
                WHERE l.warehouse_id = :w
                  AND l.item_id = :i
                  AND lo.lot_code IS NOT DISTINCT FROM :c
                ORDER BY l.occurred_at ASC, l.id ASC
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": norm_bc},
        )
        base["ledger"] = [dict(r) for r in rs.mappings().all()]

        # current stock：主读 stocks_lot（lot_code==batch_code）
        rs2 = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.qty), 0) AS qty, COUNT(*) AS n
                FROM stocks_lot s
                LEFT JOIN lots lo ON lo.id = s.lot_id
                WHERE s.warehouse_id = :w
                  AND s.item_id = :i
                  AND lo.lot_code IS NOT DISTINCT FROM :c
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": norm_bc},
        )
        r = rs2.mappings().first()
        if r and int(r["n"] or 0) > 0:
            base["current_stock"] = int(r["qty"] or 0)
        else:
            base["current_stock"] = 0

        return base
