# app/services/stock_fallbacks.py
# FEFO 提示器：v2 版本（warehouse_id, item_id, batch_code 粒度）

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
    v2 时代不再使用 batch_id，统一 batch_code。
    """

    stock_id: int
    batch_code: Optional[str]
    take_qty: int
    expiry_date: Optional[date]


@dataclass
class FefoAllocator:
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
        params = {"item_id": item_id}

        sql = """
            SELECT
                s.id          AS stock_id,
                s.batch_code  AS batch_code,
                GREATEST(COALESCE(s.qty, 0), 0) AS avail,
                b.expiry_date AS expiry_date
            FROM   stocks s
            LEFT   JOIN batches b
              ON  b.item_id      = s.item_id
             AND b.warehouse_id  = s.warehouse_id
             AND b.batch_code IS NOT DISTINCT FROM s.batch_code
            WHERE  s.item_id = :item_id
              AND  GREATEST(COALESCE(s.qty, 0), 0) > 0
        """

        if warehouse_id is not None:
            sql += " AND s.warehouse_id = :warehouse_id"
            params["warehouse_id"] = warehouse_id

        if not allow_expired:
            sql += " AND (b.expiry_date IS NULL OR b.expiry_date > NOW())"

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
            item_id=item_id,
            warehouse_id=warehouse_id,
            allow_expired=allow,
        )
        return self._plan(self._rank(rows), need_qty)
