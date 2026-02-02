# app/services/ledger_timeline_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code

_NULL_BATCH_KEY = "__NULL_BATCH__"


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

    ✅ 主线 B：查询维度统一切 batch_code_key，消灭 NULL= NULL 吞数据问题。
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
        - warehouse_id / item_id / batch_code / batch_code_key
        - delta / after_qty
        """
        cond = ["occurred_at >= :t1", "occurred_at <= :t2"]
        params: Dict[str, Any] = {"t1": time_from, "t2": time_to}

        if warehouse_id is not None:
            cond.append("warehouse_id = :w")
            params["w"] = warehouse_id

        if item_id is not None:
            cond.append("item_id = :i")
            params["i"] = item_id

        # ✅ 主线 B：batch_code 过滤统一映射到 batch_code_key
        # - 不传：不加过滤
        # - 传 "" / "None"：归一为 None -> batch_code_key='__NULL_BATCH__'
        # - 传 "Bxxx"：batch_code_key='Bxxx'
        norm_bc = normalize_optional_batch_code(batch_code)
        if batch_code is not None:
            key = _NULL_BATCH_KEY if norm_bc is None else norm_bc
            cond.append("batch_code_key = :bkey")
            params["bkey"] = key

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
                batch_code_key,
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
