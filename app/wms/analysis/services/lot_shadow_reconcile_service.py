# app/wms/inventory/services/lot_shadow_reconcile_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import normalize_optional_lot_code


class LotShadowReconcileService:
    """
    Phase 3（结构收口后的 ledger-only 影子对账）：

    - 只读 stock_ledger（lots 不再承载日期字段；batch_code_key 语义已退场）
    - 给出：
      1) lot 覆盖率（整体 + receipt 口径）
      2) 按 lot 聚合的 sum(delta)（影子余额）
      3) ledger 日期违规/污染清单（非 RECEIPT 行携带日期；理论上应永远为 0）
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
        violation_limit: int = 50,
    ) -> Dict[str, Any]:
        w = int(warehouse_id)
        i = int(item_id)
        t1 = time_from
        t2 = time_to

        # 1) 覆盖率 / 聚合 / 违规清单共用条件
        cond = ["l.warehouse_id=:w", "l.item_id=:i", "l.occurred_at>=:t1", "l.occurred_at<=:t2"]
        params: Dict[str, Any] = {"w": w, "i": i, "t1": t1, "t2": t2}

        if lot_id is not None:
            cond.append("l.lot_id=:lot")
            params["lot"] = int(lot_id)

        # batch_code 视为展示码 lots.lot_code（支持 NULL 语义）
        if batch_code is not None:
            norm_bc = normalize_optional_lot_code(batch_code)
            cond.append("lo.lot_code IS NOT DISTINCT FROM :bc")
            params["bc"] = norm_bc

        join_lots = "JOIN lots lo ON lo.id = l.lot_id"

        coverage_sql = f"""
            SELECT
              COUNT(*)::int AS total_rows,
              COUNT(l.lot_id)::int AS rows_with_lot,
              COUNT(*) FILTER (WHERE l.reason_canon='RECEIPT')::int AS receipt_rows,
              COUNT(l.lot_id) FILTER (WHERE l.reason_canon='RECEIPT')::int AS receipt_rows_with_lot
            FROM stock_ledger l
            {join_lots}
            WHERE {" AND ".join(cond)}
        """
        cov = (await session.execute(text(coverage_sql), params)).mappings().first() or {}
        coverage = {
            "total_rows": int(cov.get("total_rows") or 0),
            "rows_with_lot": int(cov.get("rows_with_lot") or 0),
            "receipt_rows": int(cov.get("receipt_rows") or 0),
            "receipt_rows_with_lot": int(cov.get("receipt_rows_with_lot") or 0),
        }

        by_lot_sql = f"""
            SELECT
              l.lot_id,
              COUNT(*)::int AS row_count,
              COALESCE(SUM(l.delta),0)::int AS sum_delta,
              MIN(l.occurred_at) AS first_occurred_at,
              MAX(l.occurred_at) AS last_occurred_at
            FROM stock_ledger l
            {join_lots}
            WHERE {" AND ".join(cond)}
            GROUP BY l.lot_id
            ORDER BY l.lot_id NULLS FIRST
        """
        by_lot = (await session.execute(text(by_lot_sql), params)).mappings().all()

        violation_sql = f"""
            SELECT
              l.id AS ledger_id,
              l.lot_id AS lot_id,
              l.reason_canon::text AS reason_canon,
              l.production_date::text AS production_date,
              l.expiry_date::text AS expiry_date,
              l.occurred_at AS occurred_at
            FROM stock_ledger l
            {join_lots}
            WHERE {" AND ".join(cond)}
              AND l.lot_id IS NOT NULL
              AND l.reason_canon <> 'RECEIPT'
              AND (l.production_date IS NOT NULL OR l.expiry_date IS NOT NULL)
            ORDER BY l.occurred_at DESC, l.id DESC
            LIMIT :lim
        """
        params2 = dict(params)
        params2["lim"] = int(violation_limit)
        violations = (await session.execute(text(violation_sql), params2)).mappings().all()

        violation_count_sql = f"""
            SELECT COUNT(*)::int AS cnt
            FROM stock_ledger l
            {join_lots}
            WHERE {" AND ".join(cond)}
              AND l.lot_id IS NOT NULL
              AND l.reason_canon <> 'RECEIPT'
              AND (l.production_date IS NOT NULL OR l.expiry_date IS NOT NULL)
        """
        violation_cnt_row = (await session.execute(text(violation_count_sql), params)).mappings().first() or {}
        violation_count = int(violation_cnt_row.get("cnt") or 0)

        return {
            "warehouse_id": w,
            "item_id": i,
            "time_from": t1,
            "time_to": t2,
            "coverage": coverage,
            "by_lot": [dict(r) for r in by_lot],
            "violation_count": violation_count,
            "violations": [dict(r) for r in violations],
        }
