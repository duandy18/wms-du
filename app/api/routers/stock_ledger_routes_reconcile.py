# app/api/routers/stock_ledger_routes_reconcile.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.routers.stock_ledger_helpers import normalize_time_range
from app.db.session import get_session
from app.schemas.stock_ledger import LedgerQuery, LedgerReconcileResult, LedgerReconcileRow

_NULL_BATCH_KEY = "__NULL_BATCH__"


def register(router: APIRouter) -> None:
    @router.post("/reconcile", response_model=LedgerReconcileResult)
    async def reconcile_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerReconcileResult:
        """
        台账对账接口（Phase 4E 真收口）：

        在指定时间窗口内（基于 occurred_at），对比：

          SUM(stock_ledger.delta)  vs  SUM(stocks_lot.qty by batch_code_key)

        找出 (warehouse_id, item_id, batch_code_key) 维度上“不平”的记录。

        规则：
        - current 余额读取统一来自 stocks_lot
        - batch_code 仅为展示码（lots.lot_code），维度事实为 batch_code_key
        - 禁止任何执行路径读取 legacy stocks
        """
        time_from, time_to = normalize_time_range(payload)

        fields_set = getattr(payload, "model_fields_set", set())
        batch_key_filter: str | None = None
        if "batch_code" in fields_set:
            norm_bc = normalize_optional_batch_code(getattr(payload, "batch_code", None))
            batch_key_filter = _NULL_BATCH_KEY if norm_bc is None else norm_bc

        wh_filter = payload.warehouse_id
        item_filter = payload.item_id

        sql = """
        WITH ledger_agg AS (
            SELECT
                warehouse_id,
                item_id,
                batch_code_key,
                -- 展示用：取任意一个 batch_code（同 key 下应一致：NULL 或某字符串）
                MAX(batch_code) AS batch_code,
                SUM(delta) AS ledger_sum_delta
            FROM stock_ledger
            WHERE occurred_at >= :time_from
              AND occurred_at <= :time_to
              AND (:wh_id IS NULL OR warehouse_id = :wh_id)
              AND (:item_id IS NULL OR item_id = :item_id)
              AND (:batch_key IS NULL OR batch_code_key = :batch_key)
            GROUP BY warehouse_id, item_id, batch_code_key
        ),
        lot_agg AS (
            SELECT
                s.warehouse_id,
                s.item_id,
                COALESCE(lo.lot_code, :null_batch_key) AS batch_code_key,
                COALESCE(SUM(s.qty), 0) AS stock_qty
            FROM stocks_lot s
            LEFT JOIN lots lo ON lo.id = s.lot_id
            WHERE (:wh_id IS NULL OR s.warehouse_id = :wh_id)
              AND (:item_id IS NULL OR s.item_id = :item_id)
              AND (:batch_key IS NULL OR COALESCE(lo.lot_code, :null_batch_key) = :batch_key)
            GROUP BY s.warehouse_id, s.item_id, COALESCE(lo.lot_code, :null_batch_key)
        )
        SELECT
            l.warehouse_id,
            l.item_id,
            l.batch_code,
            l.batch_code_key,
            l.ledger_sum_delta,
            COALESCE(a.stock_qty, 0) AS stock_qty
        FROM ledger_agg l
        LEFT JOIN lot_agg a
          ON a.warehouse_id = l.warehouse_id
         AND a.item_id = l.item_id
         AND a.batch_code_key = l.batch_code_key
        WHERE l.ledger_sum_delta != COALESCE(a.stock_qty, 0)
        ORDER BY l.warehouse_id, l.item_id, l.batch_code_key
        """

        result = await session.execute(
            __import__("sqlalchemy").text(sql),
            {
                "time_from": time_from,
                "time_to": time_to,
                "wh_id": wh_filter,
                "item_id": item_filter,
                "batch_key": batch_key_filter,
                "null_batch_key": _NULL_BATCH_KEY,
            },
        )

        rows: list[LedgerReconcileRow] = []
        for row in result.mappings():
            wh_id = int(row["warehouse_id"])
            item_id = int(row["item_id"])
            batch_code = row["batch_code"]
            ledger_sum = int(row["ledger_sum_delta"] or 0)
            stock_qty = int(row["stock_qty"] or 0)
            diff = ledger_sum - stock_qty

            rows.append(
                LedgerReconcileRow(
                    warehouse_id=wh_id,
                    item_id=item_id,
                    batch_code=batch_code,
                    ledger_sum_delta=ledger_sum,
                    stock_qty=stock_qty,
                    diff=diff,
                )
            )

        return LedgerReconcileResult(rows=rows)
