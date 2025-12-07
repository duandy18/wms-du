# app/services/ledger_timeline_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LedgerTimelineService:
    """
    Ledger Timeline Service
    -----------------------
    输出台账事件的“时间线视图”（按 occurred_at 升序），
    并且支持以 trace/ref 分组。

    用途：
    - 事件溯源
    - 并发顺序审计
    - 订单/盘点/出库链路还原
    """

    @staticmethod
    async def fetch_timeline(
        session: AsyncSession,
        *,
        time_from: datetime,
        time_to: datetime,
        warehouse_id: int | None = None,
        item_id: int | None = None,
        batch_code: str | None = None,
        trace_id: str | None = None,
        ref: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        输出 timeline 列表，每条事件完整字段：
        - occurred_at
        - movement_type
        - reason / ref / ref_line / trace_id
        - warehouse_id / item_id / batch_code
        - delta / after_qty
        """

        cond = ["occurred_at >= :t1", "occurred_at <= :t2"]

        params = {"t1": time_from, "t2": time_to}

        if warehouse_id:
            cond.append("warehouse_id = :w")
            params["w"] = warehouse_id

        if item_id:
            cond.append("item_id = :i")
            params["i"] = item_id

        if batch_code:
            cond.append("batch_code = :b")
            params["b"] = batch_code

        if trace_id:
            cond.append("trace_id = :trace")
            params["trace"] = trace_id

        if ref:
            cond.append("ref = :ref")
            params["ref"] = ref

        sql = f"""
            SELECT
                id,
                occurred_at,
                created_at,
                reason,
                ref,
                ref_line,
                trace_id,
                warehouse_id,
                item_id,
                batch_code,
                delta,
                after_qty,
                CASE
                    WHEN reason IN ('RECEIPT','INBOUND','INBOUND_RECEIPT') THEN 'INBOUND'
                    WHEN reason IN ('SHIP','SHIPMENT','OUTBOUND_SHIP','OUTBOUND_COMMIT') THEN 'OUTBOUND'
                    WHEN reason IN ('COUNT','STOCK_COUNT','INVENTORY_COUNT') THEN 'COUNT'
                    WHEN reason IN ('ADJUST','ADJUSTMENT','MANUAL_ADJUST') THEN 'ADJUST'
                    WHEN reason IN ('RETURN','RMA','INBOUND_RETURN') THEN 'RETURN'
                    ELSE 'UNKNOWN'
                END AS movement_type
            FROM stock_ledger
            WHERE {" AND ".join(cond)}
            ORDER BY occurred_at ASC, id ASC;
        """

        rs = (await session.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rs]
