# app/api/routers/stock_ledger_routes_reconcile.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import normalize_optional_lot_code
from app.api.routers.stock_ledger_helpers import normalize_time_range
from app.db.session import get_session
from app.schemas.stock_ledger import LedgerQuery, LedgerReconcileResult, LedgerReconcileRow


def register(router: APIRouter) -> None:
    @router.post("/reconcile", response_model=LedgerReconcileResult)
    async def reconcile_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerReconcileResult:
        """
        台账对账接口（Phase 3 终态：lot-only）：

        在指定时间窗口内（基于 occurred_at），对比：

          SUM(stock_ledger.delta by lot_id)  vs  stocks_lot.qty (by lot_id)

        找出 (warehouse_id, item_id, lot_id) 维度上“不平”的记录。

        规则：
        - current 余额读取统一来自 stocks_lot
        - batch_code 仅为展示码（lots.lot_code）
        - 禁止任何执行路径读取 legacy stocks
        """
        time_from, time_to = normalize_time_range(payload)

        wh_filter = payload.warehouse_id
        item_filter = payload.item_id
        lot_filter = getattr(payload, "lot_id", None)

        fields_set = getattr(payload, "model_fields_set", set())
        bc_filter = None
        if "batch_code" in fields_set:
            bc_filter = normalize_optional_lot_code(getattr(payload, "batch_code", None))

        sql = """
        WITH ledger_agg AS (
            SELECT
                l.warehouse_id,
                l.item_id,
                l.lot_id,
                lo.lot_code AS batch_code,
                SUM(l.delta) AS ledger_sum_delta
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE l.occurred_at >= :time_from
              AND l.occurred_at <= :time_to
              AND (:wh_id   IS NULL OR l.warehouse_id = :wh_id)
              AND (:item_id IS NULL OR l.item_id      = :item_id)
              AND (:lot_id  IS NULL OR l.lot_id       = :lot_id)
              AND (:bc      IS NULL OR lo.lot_code IS NOT DISTINCT FROM :bc)
            GROUP BY l.warehouse_id, l.item_id, l.lot_id, lo.lot_code
        ),
        stock_agg AS (
            SELECT
                s.warehouse_id,
                s.item_id,
                s.lot_id,
                COALESCE(SUM(s.qty), 0) AS stock_qty
            FROM stocks_lot s
            WHERE (:wh_id   IS NULL OR s.warehouse_id = :wh_id)
              AND (:item_id IS NULL OR s.item_id      = :item_id)
              AND (:lot_id  IS NULL OR s.lot_id       = :lot_id)
            GROUP BY s.warehouse_id, s.item_id, s.lot_id
        )
        SELECT
            l.warehouse_id,
            l.item_id,
            l.lot_id,
            l.batch_code,
            l.ledger_sum_delta,
            COALESCE(a.stock_qty, 0) AS stock_qty
        FROM ledger_agg l
        LEFT JOIN stock_agg a
          ON a.warehouse_id = l.warehouse_id
         AND a.item_id      = l.item_id
         AND a.lot_id       = l.lot_id
        WHERE l.ledger_sum_delta != COALESCE(a.stock_qty, 0)
        ORDER BY l.warehouse_id, l.item_id, l.lot_id
        """

        result = await session.execute(
            __import__("sqlalchemy").text(sql),
            {
                "time_from": time_from,
                "time_to": time_to,
                "wh_id": wh_filter,
                "item_id": item_filter,
                "lot_id": int(lot_filter) if lot_filter is not None else None,
                "bc": bc_filter,
            },
        )

        rows: list[LedgerReconcileRow] = []
        for row in result.mappings():
            wh_id = int(row["warehouse_id"])
            item_id = int(row["item_id"])
            lot_id = int(row["lot_id"])
            batch_code = row.get("batch_code")
            ledger_sum = int(row["ledger_sum_delta"] or 0)
            stock_qty = int(row["stock_qty"] or 0)
            diff = ledger_sum - stock_qty

            rows.append(
                LedgerReconcileRow(
                    warehouse_id=wh_id,
                    item_id=item_id,
                    batch_code=batch_code,
                    lot_code=batch_code,
                    ledger_sum_delta=ledger_sum,
                    stock_qty=stock_qty,
                    diff=diff,
                    # 额外信息：lot_id（若 schema 不含该字段，Pydantic 会忽略；含则更好）
                    lot_id=lot_id,  # type: ignore[arg-type]
                )
            )

        return LedgerReconcileResult(rows=rows)
