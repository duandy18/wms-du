# app/wms/shared/services/expiry_analytics_allocator.py
# Expiry analytics allocator (read-only suggestion; NOT an execution strategy)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

PLAN_EPSILON = 1e-6


class Allocation(TypedDict):
    """
    最小拣货计划单元（仅建议，不扣减）

    语义：
    - stock_id   : lot_id
    - batch_code : lots.lot_code（展示用）
    - expiry_date: 从 ledger 的 RECEIPT 时间事实推导出的最早 expiry
    """

    stock_id: int
    batch_code: Optional[str]
    take_qty: int
    expiry_date: Optional[date]


@dataclass
class ExpiryAnalyticsAllocator:
    """
    只读建议器（分析域）：
    - 只读 lot-world：stocks_lot + lots
    - 时间事实（expiry_date）来自 stock_ledger（reason_canon='RECEIPT'）
    - 用于“临期风险 / 老化分析 / FEFO 贴合度”类指标，不参与执行域扣减
    """

    allow_expired: bool = False

    @staticmethod
    def _sort_key(row: dict) -> tuple:
        exp = row.get("expiry_date")
        sid = row.get("stock_id")
        return (exp is None, exp, int(sid))

    def _rank(self, rows: Sequence[dict]) -> List[dict]:
        return sorted(rows, key=self._sort_key)

    def _plan(self, ranked: Sequence[dict], need_qty: int) -> List[Allocation]:
        remain = int(need_qty)
        plan: List[Allocation] = []

        for r in ranked:
            if remain <= 0:
                break
            avail_raw = float(r.get("avail", 0.0))
            avail_int = max(int(avail_raw + PLAN_EPSILON), 0)
            if avail_int <= 0:
                continue

            take_int = min(avail_int, remain)
            plan.append(
                Allocation(
                    stock_id=int(r["stock_id"]),
                    batch_code=r.get("batch_code"),
                    take_qty=take_int,
                    expiry_date=r.get("expiry_date"),
                )
            )
            remain -= take_int

        return plan

    async def _fetch_stocks(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: Optional[int],
        allow_expired: bool,
    ) -> List[dict]:
        params: dict[str, object] = {"item_id": int(item_id)}

        sql = """
            SELECT
                s.lot_id AS stock_id,
                l.lot_code AS batch_code,
                GREATEST(COALESCE(s.qty, 0), 0) AS avail,
                led.expiry_date AS expiry_date
            FROM   stocks_lot s
            LEFT   JOIN lots l
              ON  l.id = s.lot_id
            LEFT JOIN LATERAL (
                SELECT MIN(sl.expiry_date) AS expiry_date
                  FROM stock_ledger sl
                 WHERE sl.warehouse_id = s.warehouse_id
                   AND sl.item_id      = s.item_id
                   AND sl.lot_id       = s.lot_id
                   AND sl.reason_canon = 'RECEIPT'
            ) led ON TRUE
            WHERE  s.item_id = :item_id
              AND  GREATEST(COALESCE(s.qty, 0), 0) > 0
        """

        if warehouse_id is not None:
            sql += " AND s.warehouse_id = :warehouse_id"
            params["warehouse_id"] = int(warehouse_id)

        if not allow_expired:
            sql += " AND (led.expiry_date IS NULL OR led.expiry_date > CURRENT_DATE)"

        res: Result = await session.execute(text(sql), params)
        return [dict(r._mapping) for r in res]

    async def allocate(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        need_qty: int,
        warehouse_id: Optional[int] = None,
        allow_expired: Optional[bool] = None,
    ) -> List[Allocation]:
        allow = self.allow_expired if allow_expired is None else bool(allow_expired)
        rows = await self._fetch_stocks(
            session,
            item_id=int(item_id),
            warehouse_id=warehouse_id,
            allow_expired=allow,
        )
        return self._plan(self._rank(rows), int(need_qty))
