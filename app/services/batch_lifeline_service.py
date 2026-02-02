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

    ✅ 主线 B：统一维度使用 batch_code_key（COALESCE(batch_code,'__NULL_BATCH__')）
    - 允许 batch_code 为 NULL（无批次槽位）
    - 禁止 'None' 字符串回潮（入口归一）
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

        base = {
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "batch_code": norm_bc,
            "batch_code_key": batch_code_key,
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

        # current stock（按 batch_code_key 维度对齐 NULL 语义）
        rs = await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE warehouse_id=:w AND item_id=:i AND batch_code_key=:ck
            """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "ck": str(batch_code_key)},
        )
        row = rs.mappings().first()
        base["current_stock"] = int(row["qty"]) if row else 0

        return base
