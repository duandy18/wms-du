# app/wms/outbound/services/outbound_commit_service.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.lot_code_contract import fetch_item_expiry_policy_map
from app.core.problem import raise_problem
from app.wms.outbound.services.invariant_guard_outbound import enforce_outbound_invariant_guard
from app.wms.outbound.services.order_fulfillment_service import OrderFulfillmentService
from app.oms.services.order_ref_resolver import resolve_order_id
from app.wms.outbound.contracts.outbound_commit_models import (
    ShipLine,
    coerce_line,
    norm_batch_code,
    problem_error_code_from_http_exc_detail,
)
from app.wms.stock.services.stock_service import StockService

UTC = timezone.utc


async def _load_existing_order_id(session: AsyncSession, *, order_ref: str) -> int:
    s = str(order_ref or "").strip()
    if not s:
        raise ValueError("order_id/order_ref cannot be empty")

    return int(await resolve_order_id(session, order_ref=s))


def _norm_lot_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


async def _resolve_lot_id_by_lot_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> Optional[int]:
    code = _norm_lot_code(lot_code)
    if not code:
        return None

    rows = (
        await session.execute(
            sa.text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 ORDER BY id ASC
                 LIMIT 2
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": str(code)},
        )
    ).all()

    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError("supplier_lot_code_ambiguous")

    return int(rows[0][0])


class OutboundService:
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
        warehouse_code: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        _ = warehouse_code

        ts = occurred_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = datetime.now(UTC)

        order_ref = str(order_id).strip()
        if not order_ref:
            raise ValueError("order_id/order_ref cannot be empty")

        order_pk = await _load_existing_order_id(session, order_ref=order_ref)

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

        if len(wh_set) != 1:
            raise ValueError(f"Phase 5: ship lines must have exactly 1 warehouse_id, got={sorted(wh_set)}")
        actual_wh_id = int(next(iter(wh_set)))

        item_ids = {int(item_id) for (item_id, _wh_id, _bc) in agg_qty.keys()}
        expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)
        missing_items = [int(i) for i in sorted(item_ids) if i not in expiry_policy_map]
        if missing_items:
            raise_problem(
                status_code=422,
                error_code="unknown_item",
                message="存在未知商品，禁止提交出库。",
                context={"order_id": str(order_ref), "missing_item_ids": missing_items},
                details=[{"type": "validation", "path": "lines[item_id]", "item_ids": missing_items, "reason": "unknown"}],
            )

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
            need = int(want_qty) + already

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

            requires_batch = _requires_batch_from_expiry_policy(expiry_policy_map.get(int(item_id)))

            try:
                if requires_batch and (batch_code is not None) and (lot_id is not None):
                    res = await self.stock_svc.adjust_lot(
                        session=session,
                        item_id=item_id,
                        warehouse_id=wh_id,
                        lot_id=int(lot_id),
                        delta=-need,
                        reason="OUTBOUND_SHIP",
                        ref=str(order_ref),
                        ref_line=1,
                        occurred_at=ts,
                        trace_id=trace_id,
                        batch_code=batch_code,
                        meta={"sub_reason": "ORDER_SHIP", "order_id": int(order_pk)},
                        production_date=None,
                        expiry_date=None,
                    )
                else:
                    res = await self.stock_svc.adjust(
                        session=session,
                        item_id=item_id,
                        delta=-need,
                        reason="OUTBOUND_SHIP",
                        ref=str(order_ref),
                        ref_line=1,
                        occurred_at=ts,
                        warehouse_id=wh_id,
                        batch_code=batch_code,
                        trace_id=trace_id,
                        meta={"sub_reason": "ORDER_SHIP", "order_id": int(order_pk)},
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
                        "lot_id": res.get("lot_id") or lot_id,
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

            except ValueError as e:
                msg = str(e)
                if msg == "supplier_lot_code_ambiguous":
                    results.append(
                        {
                            "item_id": item_id,
                            "batch_code": batch_code,
                            "warehouse_id": wh_id,
                            "qty": need,
                            "status": "REJECTED",
                            "error_code": "supplier_lot_code_ambiguous",
                            "error": msg,
                        }
                    )
                elif "insufficient stock" in msg.lower():
                    results.append(
                        {
                            "item_id": item_id,
                            "batch_code": batch_code,
                            "warehouse_id": wh_id,
                            "qty": need,
                            "status": "INSUFFICIENT",
                            "error_code": "insufficient_stock",
                            "error": msg,
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
                            "error_code": "reject",
                            "error": msg,
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

        if total_qty > 0:
            await enforce_outbound_invariant_guard(session, ref=str(order_ref), at=ts)

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
