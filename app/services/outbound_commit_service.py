# app/services/outbound_commit_service.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.services.invariant_guard_outbound import enforce_outbound_invariant_guard
from app.services.order_fulfillment_service import OrderFulfillmentService
from app.services.order_ref_resolver import resolve_order_id
from app.services.outbound_commit_models import (
    ShipLine,
    coerce_line,
    norm_batch_code,
    problem_error_code_from_http_exc_detail,
)
from app.services.stock_service import StockService

UTC = timezone.utc


async def _resolve_lot_id_by_lot_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> Optional[int]:
    """
    用展示码 lot_code（旧名 batch_code）解析 lot_id。
    lot_code 非 NULL 时，(wh,item,lot_code) 应唯一（uq_lots_wh_item_lot_code）。
    """
    row = (
        await session.execute(
            sa.text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code     = :c
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": str(lot_code)},
        )
    ).first()
    return int(row[0]) if row else None


class OutboundService:
    """
    Phase 5 第二刀：order_fulfillment 成为唯一执行仓事实（authority）。

    - 外部仍可传字符串 order_ref（平台单号/ORD:...），但必须可硬解析到 orders.id
    - fulfillment 以 orders.id 为主键写入执行事实（planned/actual）
    - 出库事实用 ship_committed_at / shipped_at 表达（不再用 fulfillment_status 阶段机）
    - 库存写入仍通过 StockService（stocks_lot + stock_ledger）
    - 执行尾门：Invariant Guard（不触 snapshot）
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()
        self.fulfillment_svc = OrderFulfillmentService()

    async def commit(
        self,
        session: AsyncSession,
        *,
        order_id: str | int,
        lines: Sequence[Dict[str, Any] | ShipLine],
        occurred_at: Optional[datetime] = None,
        warehouse_code: Optional[str] = None,  # 保留旧签名，当前实现不使用
        trace_id: Optional[str] = None,  # 上层可携带 trace_id
    ) -> Dict[str, Any]:
        _ = warehouse_code

        ts = occurred_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = datetime.now(UTC)

        order_ref = str(order_id).strip()
        if not order_ref:
            raise ValueError("order_id/order_ref cannot be empty")

        # ✅ Phase 5：硬解析外部 order_ref -> orders.id（解析失败直接拒绝，不执行扣库）
        order_pk = await resolve_order_id(session, order_ref=order_ref)

        # ✅ 聚合维度：item + wh + batch_code(展示码，允许 NULL)
        agg_qty: Dict[Tuple[int, int, Optional[str]], int] = defaultdict(int)
        wh_set: set[int] = set()

        for raw in lines:
            ln = coerce_line(raw)
            if ln.warehouse_id is None:
                raise ValueError("warehouse_id is required in each ship line")
            wh_id = int(ln.warehouse_id)
            wh_set.add(wh_id)

            key = (int(ln.item_id), wh_id, norm_batch_code(ln.batch_code))
            agg_qty[key] += int(ln.qty)

        if not agg_qty:
            return {
                "status": "OK",
                "order_id": str(order_ref),
                "order_pk": int(order_pk),
                "total_qty": 0,
                "committed_lines": 0,
                "results": [],
                "ship_committed_at": None,
                "shipped_at": None,
            }

        # ✅ Phase 5：同一订单一次 SHIP 只能一个执行仓（否则就是 split-ship，需要显式模型）
        if len(wh_set) != 1:
            raise ValueError(f"Phase 5: ship lines must have exactly 1 warehouse_id, got={sorted(wh_set)}")
        actual_wh_id = int(next(iter(wh_set)))

        # ✅ 出库锚点事实：先确保 ship_committed_at（或幂等确认已存在）
        f0 = await self.fulfillment_svc.ensure_ship_committed(
            session,
            order_id=int(order_pk),
            warehouse_id=int(actual_wh_id),
            at=ts,
        )

        committed = 0
        total_qty = 0
        results: List[Dict[str, Any]] = []

        for (item_id, wh_id, batch_code), want_qty in agg_qty.items():
            # ✅ 幂等查询以 ledger 为准：
            # - batch_code 非空：可唯一解析 lot_id -> 幂等按 lot_id 精确统计
            # - batch_code 为空：对“非批次商品”允许存在多个 INTERNAL lot，幂等按 (ref,item,wh) 汇总避免漂移
            lot_id: int | None = None
            if batch_code is not None:
                lot_id = await _resolve_lot_id_by_lot_code(
                    session,
                    warehouse_id=int(wh_id),
                    item_id=int(item_id),
                    lot_code=str(batch_code),
                )

            if lot_id is not None:
                row = await session.execute(
                    sa.text(
                        """
                        SELECT COALESCE(SUM(delta), 0)
                        FROM stock_ledger
                        WHERE ref=:ref
                          AND item_id=:item
                          AND warehouse_id=:wid
                          AND lot_id=:lot
                          AND delta < 0
                        """
                    ),
                    {"ref": str(order_ref), "item": item_id, "wid": wh_id, "lot": int(lot_id)},
                )
            else:
                row = await session.execute(
                    sa.text(
                        """
                        SELECT COALESCE(SUM(delta), 0)
                        FROM stock_ledger
                        WHERE ref=:ref
                          AND item_id=:item
                          AND warehouse_id=:wid
                          AND delta < 0
                        """
                    ),
                    {"ref": str(order_ref), "item": item_id, "wid": wh_id},
                )

            already = int(row.scalar() or 0)
            need = int(want_qty) + already  # 目标是总 delta = -want_qty

            if need <= 0:
                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": int(want_qty),
                        "status": "OK",
                        "idempotent": True,
                    }
                )
                continue

            try:
                res = await self.stock_svc.adjust(
                    session=session,
                    item_id=item_id,
                    delta=-need,
                    reason="OUTBOUND_SHIP",
                    ref=str(order_ref),
                    ref_line=1,
                    occurred_at=ts,
                    warehouse_id=wh_id,
                    batch_code=batch_code,  # 展示码输入（可为空）
                    trace_id=trace_id,
                    meta={
                        "sub_reason": "ORDER_SHIP",
                        "order_id": int(order_pk),
                    },
                )
                committed += 1
                total_qty += need

                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": need,
                        "status": "OK",
                        "after": res.get("after"),
                        "lot_id": res.get("lot_id"),
                    }
                )

            except HTTPException as e:
                code = problem_error_code_from_http_exc_detail(getattr(e, "detail", None))
                if e.status_code == 409 and code == "insufficient_stock":
                    results.append(
                        {
                            "item_id": item_id,
                            "batch_code": batch_code,
                            "warehouse_id": wh_id,
                            "qty": need,
                            "status": "INSUFFICIENT",
                            "error_code": code,
                            "error": getattr(e, "detail", None),
                        }
                    )
                else:
                    results.append(
                        {
                            "item_id": item_id,
                            "batch_code": batch_code,
                            "warehouse_id": wh_id,
                            "qty": need,
                            "status": "REJECTED",
                            "error_code": code or "http_error",
                            "error": getattr(e, "detail", None),
                        }
                    )

            except Exception as e:
                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": need,
                        "status": "REJECTED",
                        "error_code": "internal_error",
                        "error": str(e),
                    }
                )

        # ✅ 如果发生过任何扣库写入：必须跑 Invariant Guard（确保三账闭合）
        if total_qty > 0:
            await enforce_outbound_invariant_guard(session, ref=str(order_ref), at=ts)

        # ✅ 若存在任何失败行：禁止推进 shipped_at（失败栈必须冒出来）
        has_failures = any(r.get("status") != "OK" for r in results)
        if has_failures:
            raise_problem(
                status_code=409,
                error_code="outbound_commit_reject",
                message="订单出库未完成：存在拒绝/缺货行，已禁止推进为已出库（shipped_at）。",
                context={
                    "order_id": str(order_ref),
                    "order_pk": int(order_pk),
                    "warehouse_id": int(actual_wh_id),
                    "ship_committed_at": f0.get("ship_committed_at"),
                    "ship_committed_idempotent": bool(f0.get("idempotent")),
                    "total_qty_committed": int(total_qty),
                    "committed_lines": int(committed),
                },
                details=[{"results": results}],
                next_actions=[
                    {"action": "fix_lines_and_retry", "label": "修复缺货/错误行后重试出库"},
                    {"action": "inspect_fulfillment", "label": "检查订单履约记录（ship_committed_at）"},
                ],
            )
            return {}

        # ✅ 全部 OK：推进 shipped_at（事实）
        f1 = await self.fulfillment_svc.mark_shipped(session, order_id=int(order_pk), at=ts)

        return {
            "status": "OK",
            "order_id": str(order_ref),
            "order_pk": int(order_pk),
            "total_qty": total_qty,
            "committed_lines": committed,
            "results": results,
            "ship_committed_at": f0.get("ship_committed_at"),
            "shipped_at": f1.get("shipped_at"),
        }


async def ship_commit(
    session: AsyncSession,
    order_id: str | int,
    lines: Sequence[Dict[str, Any] | ShipLine],
    warehouse_code: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    svc = OutboundService()
    return await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        warehouse_code=warehouse_code,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )


commit_outbound = ship_commit
