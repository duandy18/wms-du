# app/services/outbound_commit_service.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService
from app.services.three_books_enforcer import enforce_three_books

from app.services.outbound_commit_models import (
    ShipLine,
    batch_key,
    coerce_line,
    norm_batch_code,
    problem_error_code_from_http_exc_detail,
)

UTC = timezone.utc


class OutboundService:
    """
    Phase 3 出库服务（硬口径 + 强幂等）：

    - 粒度：(warehouse_id, item_id, batch_code|NULL)
    - 幂等：以 (ref=order_id, item_id, warehouse_id, batch_code_key) 为键，
      先查已扣数量，再扣“剩余需要扣”的量。
    - 同一 payload 中重复的 (item,wh,batch) 会先合并为一行，再做一次扣减。

    Phase 3.6：增加 trace_id 透传能力（当前不直接写 audit，仅向下传参）。
    Phase 3.7-A：trace_id 透传到 StockService.adjust，用于后续填充 stock_ledger.trace_id。

    Phase 3.10：
    - 引入 sub_reason（业务细分）：
      订单发货出库：sub_reason = ORDER_SHIP

    Phase 3（三库一致性工程化）：
    - commit 成功的必要条件：ledger + stocks + snapshot 可观测一致（对本次 touched keys）
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

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

        # ✅ 聚合维度：item + wh + batch_code（允许 NULL）
        agg_qty: Dict[Tuple[int, int, Optional[str]], int] = defaultdict(int)
        for raw in lines:
            ln = coerce_line(raw)
            if ln.warehouse_id is None:
                raise ValueError("warehouse_id is required in each ship line")
            key = (int(ln.item_id), int(ln.warehouse_id), norm_batch_code(ln.batch_code))
            agg_qty[key] += int(ln.qty)

        committed = 0
        total_qty = 0
        results: List[Dict[str, Any]] = []

        # Phase 3：收集本次出库的 effects（用于三库一致性验证）
        effects: List[Dict[str, Any]] = []

        for (item_id, wh_id, batch_code), want_qty in agg_qty.items():
            ck = batch_key(batch_code)

            # ✅ 幂等查询：用 batch_code_key（NULL 语义稳定）
            row = await session.execute(
                sa.text(
                    """
                    SELECT COALESCE(SUM(delta), 0)
                    FROM stock_ledger
                    WHERE ref=:ref
                      AND item_id=:item
                      AND warehouse_id=:wid
                      AND batch_code_key=:ck
                      AND delta < 0
                    """
                ),
                {"ref": str(order_id), "item": item_id, "wid": wh_id, "ck": ck},
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
                    ref=str(order_id),
                    ref_line=1,
                    occurred_at=ts,
                    warehouse_id=wh_id,
                    batch_code=batch_code,  # ✅ may be NULL
                    trace_id=trace_id,
                    meta={
                        "sub_reason": "ORDER_SHIP",
                    },
                )
                committed += 1
                total_qty += need

                effects.append(
                    {
                        "warehouse_id": int(wh_id),
                        "item_id": int(item_id),
                        "batch_code": batch_code,  # ✅ keep None, do NOT str()
                        "qty": -int(need),
                        "ref": str(order_id),
                        "ref_line": 1,
                    }
                )

                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": need,
                        "status": "OK",
                        "after": res.get("after"),
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

        if effects:
            await enforce_three_books(session, ref=str(order_id), effects=effects, at=ts)

        return {
            "status": "OK",
            "order_id": str(order_id),
            "total_qty": total_qty,
            "committed_lines": committed,
            "results": results,
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
