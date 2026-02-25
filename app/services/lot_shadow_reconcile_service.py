# app/services/lot_shadow_reconcile_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code

_NULL_BATCH_KEY = "__NULL_BATCH__"


def _batch_key(batch_code: Optional[str]) -> Optional[str]:
    """
    None 表示“不按 batch 过滤”（全量 batch 槽位）。
    若用户显式传了 batch_code（可能是 ""/"None"），上层会把 payload.batch_code 归一。
    这里提供一个 helper 给 router/service 更清晰。
    """
    if batch_code is None:
        return None
    norm = normalize_optional_batch_code(batch_code)
    return _NULL_BATCH_KEY if norm is None else str(norm)


class LotShadowReconcileService:
    """
    Phase 4A-2a / Step C: lot 维度影子对账（最小可落地版）

    - 不改 stocks 槽位世界观
    - 只读 stock_ledger + lots
    - 给出：
      1) lot 覆盖率（整体 + receipt 口径）
      2) 按 lot 聚合的 sum(delta)（影子余额）
      3) ledger dates vs lot dates 差异清单（用于数据治理/迁移准备）
    """

    @staticmethod
    async def reconcile(
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        time_from: datetime,
        time_to: datetime,
        batch_code: Optional[str] = None,
        lot_id: Optional[int] = None,
        mismatch_limit: int = 50,
    ) -> Dict[str, Any]:
        w = int(warehouse_id)
        i = int(item_id)
        t1 = time_from
        t2 = time_to

        bkey = _batch_key(batch_code)

        # 1) 覆盖率
        cond = ["warehouse_id=:w", "item_id=:i", "occurred_at>=:t1", "occurred_at<=:t2"]
        params: Dict[str, Any] = {"w": w, "i": i, "t1": t1, "t2": t2}
        if bkey is not None:
            cond.append("batch_code_key=:bkey")
            params["bkey"] = bkey
        if lot_id is not None:
            cond.append("lot_id=:lot")
            params["lot"] = int(lot_id)

        coverage_sql = f"""
            SELECT
              COUNT(*)::int AS total_rows,
              COUNT(lot_id)::int AS rows_with_lot,
              COUNT(*) FILTER (WHERE reason_canon='RECEIPT')::int AS receipt_rows,
              COUNT(lot_id) FILTER (WHERE reason_canon='RECEIPT')::int AS receipt_rows_with_lot
            FROM stock_ledger
            WHERE {" AND ".join(cond)}
        """
        cov = (await session.execute(text(coverage_sql), params)).mappings().first() or {}
        coverage = {
            "total_rows": int(cov.get("total_rows") or 0),
            "rows_with_lot": int(cov.get("rows_with_lot") or 0),
            "receipt_rows": int(cov.get("receipt_rows") or 0),
            "receipt_rows_with_lot": int(cov.get("receipt_rows_with_lot") or 0),
        }

        # 2) 按 lot 聚合（影子余额）
        by_lot_sql = f"""
            SELECT
              lot_id,
              COUNT(*)::int AS row_count,
              COALESCE(SUM(delta),0)::int AS sum_delta,
              MIN(occurred_at) AS first_occurred_at,
              MAX(occurred_at) AS last_occurred_at
            FROM stock_ledger
            WHERE {" AND ".join(cond)}
            GROUP BY lot_id
            ORDER BY lot_id NULLS FIRST
        """
        by_lot = (await session.execute(text(by_lot_sql), params)).mappings().all()

        # 3) 日期一致性（ledger vs lots）
        # 只检查有 lot_id 的行；只要两边都非空且不相等就算 mismatch
        mismatch_sql = f"""
            SELECT
              l.id AS ledger_id,
              l.lot_id AS lot_id,
              l.production_date::text AS ledger_production_date,
              lo.production_date::text AS lot_production_date,
              l.expiry_date::text AS ledger_expiry_date,
              lo.expiry_date::text AS lot_expiry_date,
              l.occurred_at AS occurred_at
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE {" AND ".join(cond)}
              AND l.lot_id IS NOT NULL
              AND (
                (l.production_date IS NOT NULL AND lo.production_date IS NOT NULL AND l.production_date <> lo.production_date)
                OR
                (l.expiry_date IS NOT NULL AND lo.expiry_date IS NOT NULL AND l.expiry_date <> lo.expiry_date)
              )
            ORDER BY l.occurred_at DESC, l.id DESC
            LIMIT :lim
        """
        params2 = dict(params)
        params2["lim"] = int(mismatch_limit)

        mismatches = (await session.execute(text(mismatch_sql), params2)).mappings().all()

        mismatch_count_sql = f"""
            SELECT COUNT(*)::int AS cnt
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE {" AND ".join(cond)}
              AND l.lot_id IS NOT NULL
              AND (
                (l.production_date IS NOT NULL AND lo.production_date IS NOT NULL AND l.production_date <> lo.production_date)
                OR
                (l.expiry_date IS NOT NULL AND lo.expiry_date IS NOT NULL AND l.expiry_date <> lo.expiry_date)
              )
        """
        mismatch_cnt_row = (await session.execute(text(mismatch_count_sql), params)).mappings().first() or {}
        mismatch_count = int(mismatch_cnt_row.get("cnt") or 0)

        return {
            "warehouse_id": w,
            "item_id": i,
            "batch_code_key": bkey,
            "time_from": t1,
            "time_to": t2,
            "coverage": coverage,
            "by_lot": [dict(r) for r in by_lot],
            "mismatch_count": mismatch_count,
            "mismatches": [dict(r) for r in mismatches],
        }
