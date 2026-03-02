# app/services/fefo_allocator.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.stock_service import StockService

JsonLike = Dict[str, Any]


def _shortage_detail(
    *,
    item_id: int,
    batch_code: Optional[str],
    available_qty: int,
    required_qty: int,
    path: str,
) -> Dict[str, Any]:
    short_qty = max(0, int(required_qty) - int(available_qty))
    return {
        "type": "shortage",
        "path": path,
        "item_id": int(item_id),
        "batch_code": batch_code,
        "required_qty": int(required_qty),
        "available_qty": int(available_qty),
        "short_qty": int(short_qty),
        # ✅ 兼容/同义字段（保留）
        "shortage_qty": int(short_qty),
        "need": int(required_qty),
        "on_hand": int(available_qty),
        "shortage": int(short_qty),
        "reason": "insufficient_stock",
    }


class FefoAllocator:
    """
    Phase M-2 终态：FEFO 分配器（lot-only）

    核心思想：
    ------------------------------------------
    • 分配维度： (warehouse_id, item_id, lot_id)
    • expiry_date 为 FEFO 核心排序依据（来自 lots.expiry_date）
    • expiry_date NULL → 排最后
    • stocks_lot.qty 为扣减余额真相
    • 强一致性：FOR UPDATE 锁 stocks_lot
    ------------------------------------------

    返回：
    - plan(): [(batch_code, take_qty)]
      其中 batch_code 为展示码 lots.lot_code（可能为 None）
    """

    def __init__(self, stock: Optional[StockService] = None) -> None:
        self.stock = stock or StockService()

    async def _load_total_available_qty(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        allow_expired: bool,
        occurred_date: date,
    ) -> int:
        if allow_expired:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(s.qty), 0)
                          FROM stocks_lot s
                         WHERE s.item_id = :item
                           AND s.warehouse_id = :wh
                           AND s.qty > 0
                        """
                    ),
                    {"item": int(item_id), "wh": int(warehouse_id)},
                )
            ).first()
        else:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(s.qty), 0)
                          FROM stocks_lot s
                          LEFT JOIN lots lo ON lo.id = s.lot_id
                         WHERE s.item_id = :item
                           AND s.warehouse_id = :wh
                           AND s.qty > 0
                           AND (lo.expiry_date IS NULL OR lo.expiry_date >= :d)
                        """
                    ),
                    {"item": int(item_id), "wh": int(warehouse_id), "d": occurred_date},
                )
            ).first()
        try:
            return int((row[0] if row else 0) or 0)
        except Exception:
            return 0

    async def plan(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        need: int,
        occurred_date: date,
        allow_expired: bool = False,
    ) -> List[Tuple[Optional[str], int]]:
        """
        （只读 + 锁）计算 FEFO 计划（lot-only）。

        排序规则：
        1) lots.expiry_date ASC（NULLS LAST）
        2) stocks_lot.lot_id ASC（稳定 tie-breaker）
        """
        sql = text(
            """
            SELECT
                s.lot_id AS lot_id,
                s.qty AS qty,
                lo.lot_code AS lot_code,
                lo.expiry_date AS exp
            FROM stocks_lot s
            LEFT JOIN lots lo ON lo.id = s.lot_id
            WHERE s.item_id = :item
              AND s.warehouse_id = :wh
              AND s.qty > 0
            ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id ASC
            FOR UPDATE OF s
            """
        )

        rows = (await session.execute(sql, {"item": int(item_id), "wh": int(warehouse_id)})).all()

        seq: List[Tuple[int, Optional[str], Optional[date], int]] = []
        for r in rows:
            lot_id = int(r.lot_id)
            lot_code = r.lot_code
            exp = r.exp
            qty = int(r.qty)
            seq.append((lot_id, lot_code, exp, qty))

        if not allow_expired:
            seq = [x for x in seq if x[2] is None or x[2] >= occurred_date]

        remaining = int(need)
        plan: List[Tuple[Optional[str], int]] = []

        for lot_id, lot_code, exp, qty in seq:
            _ = lot_id
            _ = exp
            if remaining <= 0:
                break
            take = min(remaining, int(qty))
            if take > 0:
                plan.append((lot_code, int(take)))
                remaining -= int(take)

        if remaining > 0:
            available_total = await self._load_total_available_qty(
                session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                allow_expired=bool(allow_expired),
                occurred_date=occurred_date,
            )
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，无法生成 FEFO 分配计划。",
                context={
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "allow_expired": bool(allow_expired),
                    "occurred_date": occurred_date.isoformat(),
                },
                details=[
                    _shortage_detail(
                        item_id=int(item_id),
                        batch_code=None,
                        available_qty=int(available_total),
                        required_qty=int(need),
                        path="fefo.plan.lot",
                    )
                ],
                next_actions=[
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                ],
            )

        return plan

    async def ship(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        qty: int,
        ref: str,
        occurred_at: datetime,
        reason: MovementType = MovementType.SHIPMENT,
        allow_expired: bool = False,
        start_ref_line: int = 1,
        trace_id: Optional[str] = None,
    ) -> JsonLike:
        """
        按 FEFO 计划逐 lot 扣减：
            - 每个 lot 一条 ledger（带 lot_id）
            - 写 stocks_lot（主写）
            - 可选 shadow 写 stocks（adjust_lot 默认开启）
        """
        _ = await self.plan(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            need=int(qty),
            occurred_date=occurred_at.date(),
            allow_expired=bool(allow_expired),
        )

        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        s.lot_id AS lot_id,
                        s.qty AS qty,
                        lo.lot_code AS lot_code,
                        lo.expiry_date AS exp
                    FROM stocks_lot s
                    LEFT JOIN lots lo ON lo.id = s.lot_id
                    WHERE s.item_id = :item
                      AND s.warehouse_id = :wh
                      AND s.qty > 0
                    ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id ASC
                    """
                ),
                {"item": int(item_id), "wh": int(warehouse_id)},
            )
        ).all()

        seq: List[Tuple[int, Optional[str], Optional[date], int]] = []
        for r in rows:
            lot_id = int(r.lot_id)
            lot_code = r.lot_code
            exp = r.exp
            q = int(r.qty)
            seq.append((lot_id, lot_code, exp, q))

        if not allow_expired:
            seq = [x for x in seq if x[2] is None or x[2] >= occurred_at.date()]

        legs: List[Dict[str, Any]] = []
        total = 0
        remain = int(qty)

        for idx, (lot_id, lot_code, exp, q) in enumerate(seq, start=int(start_ref_line)):
            _ = exp
            if remain <= 0:
                break
            take_qty = min(remain, int(q))
            if take_qty <= 0:
                continue

            await self.stock.adjust_lot(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_id=int(lot_id),
                delta=-int(take_qty),
                reason=reason,
                ref=str(ref),
                ref_line=int(idx),
                occurred_at=occurred_at,
                trace_id=trace_id,
                batch_code=lot_code,  # 展示码
                meta={"sub_reason": "FEFO_SHIP"},
            )

            legs.append({"batch_code": lot_code, "delta": -int(take_qty), "ref_line": int(idx)})
            total += int(take_qty)
            remain -= int(take_qty)

        return {
            "ok": True,
            "total": int(total),
            "legs": legs,
            "ref": str(ref),
        }
