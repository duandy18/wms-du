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
    FEFO v2 分配器（与 Batch v3 / Stock v3 完全对齐）

    核心思想：
    ------------------------------------------
    • 分配维度： (warehouse_id, item_id, batch_code)
      - 对非批次商品：batch_code = NULL 是合法槽位（不是未知）
    • expiry_date 为 FEFO 核心排序依据
    • expiry_date NULL → 排最后
    • stocks.qty 为库存唯一真相（batches.qty 无作用）
    • 强一致性：FOR UPDATE 锁 stocks
    • 不使用 batch_id、不使用 location_id
    ------------------------------------------

    使用方式（必须由外层控制事务）：

        async with session.begin():
            plan = await fefo.plan(...)
            await fefo.ship(...)
    """

    def __init__(self, stock: Optional[StockService] = None) -> None:
        self.stock = stock or StockService()

    # ---------------------------------------------------------------
    # 计算 FEFO 计划：返回 [(batch_code, take_qty)]
    # ---------------------------------------------------------------
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
        （只读 + 锁）计算 FEFO 计划。

        基于 stocks + batches 的最新 V3 模型，按以下顺序排序：
        1. expiry_date ASC（NULLS LAST）
        2. stock_id ASC（稳定 tie-breaker）

        ✅ 主线 B：join batches 使用 IS NOT DISTINCT FROM，避免 batch_code=NULL 吞数据。
        ✅ 支持非批次商品：batch_code 允许为 None。
        """
        sql = text(
            """
            -- 锁定 stocks（库存真实来源）
            SELECT
                s.id          AS stock_id,
                s.batch_code  AS code,
                s.qty         AS qty,
                b.expiry_date AS exp
            FROM stocks s
            LEFT JOIN batches b
              ON b.item_id = s.item_id
             AND b.warehouse_id = s.warehouse_id
             AND b.batch_code IS NOT DISTINCT FROM s.batch_code
            WHERE s.item_id = :item
              AND s.warehouse_id = :wh
              AND s.qty > 0
            FOR UPDATE OF s
            """
        )

        rows = (await session.execute(sql, {"item": item_id, "wh": warehouse_id})).all()

        # 将结果整理并排序
        seq: List[Tuple[Optional[str], Optional[date], int, int]] = []
        for r in rows:
            seq.append((r.code, r.exp, int(r.qty), int(r.stock_id)))

        # 排序规则：expiry_date ASC (NULL LAST), stock_id ASC
        seq.sort(key=lambda x: (x[1] is None, x[1], x[3]))

        # 过滤过期（需要看 occurred_date）
        if not allow_expired:
            seq = [x for x in seq if x[1] is None or x[1] >= occurred_date]

        # 贪心切片
        remaining = int(need)
        plan: List[Tuple[Optional[str], int]] = []

        for code, exp, qty, sid in seq:
            _ = exp
            _ = sid
            if remaining <= 0:
                break
            take = min(remaining, qty)
            if take > 0:
                plan.append((code, take))
                remaining -= take

        if remaining > 0:
            available = int(need) - int(remaining)
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
                        available_qty=int(available),
                        required_qty=int(need),
                        path="fefo.plan",
                    )
                ],
                next_actions=[
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                ],
            )

        return plan

    # ---------------------------------------------------------------
    # ship：根据 FEFO 计划扣减库存（必须在同一事务内）
    # ---------------------------------------------------------------
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
        按 FEFO 计划逐批扣减：
            - 每个批次一条 ledger
            - 共享事务锁保证一致性

        ✅ 支持 batch_code=None（非批次商品合法槽位），严禁 str(None)。
        """
        plan = await self.plan(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            need=qty,
            occurred_date=occurred_at.date(),
            allow_expired=allow_expired,
        )

        legs: List[Dict[str, Any]] = []
        total = 0

        for idx, (code, take_qty) in enumerate(plan, start=start_ref_line):
            # 扣减库存（库存不足会由 StockService.adjust 统一 Problem 化并透传）
            await self.stock.adjust(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                delta=-take_qty,
                reason=reason,
                ref=ref,
                ref_line=idx,
                batch_code=code,
                occurred_at=occurred_at,
                trace_id=trace_id,
            )

            legs.append({"batch_code": code, "delta": -take_qty, "ref_line": idx})
            total += take_qty

        return {
            "ok": True,
            "total": total,
            "legs": legs,
            "ref": ref,
        }
