# app/services/ledger_timeline_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import normalize_optional_lot_code


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

    ✅ Phase 3 终态（lot-only）：
    - 过滤维度以 lot_id 为准
    - batch_code 仅为展示/输入标签（lots.lot_code），不再使用 batch_code_key
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
        lot_id: int | None = None,
        trace_id: str | None = None,
        ref: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        输出 timeline 列表，每条事件完整字段：
        - occurred_at
        - movement_type
        - reason / ref / ref_line / trace_id
        - warehouse_id / item_id / batch_code(展示码 lots.lot_code)
        - lot_id
        - delta / after_qty
        """
        cond = ["l.occurred_at >= :t1", "l.occurred_at <= :t2"]
        params: Dict[str, Any] = {"t1": time_from, "t2": time_to}

        if warehouse_id is not None:
            cond.append("l.warehouse_id = :w")
            params["w"] = int(warehouse_id)

        if item_id is not None:
            cond.append("l.item_id = :i")
            params["i"] = int(item_id)

        if lot_id is not None:
            cond.append("l.lot_id = :lot")
            params["lot"] = int(lot_id)

        # ✅ batch_code 过滤：视为展示码 lots.lot_code（支持 NULL 语义）
        # - 不传：不加过滤
        # - 传 "" / "None"：归一为 None -> lo.lot_code IS NULL
        # - 传 "Bxxx"：lo.lot_code = 'Bxxx'
        if batch_code is not None:
            norm_bc = normalize_optional_lot_code(batch_code)
            cond.append("lo.lot_code IS NOT DISTINCT FROM :bc")
            params["bc"] = norm_bc

        if trace_id:
            cond.append("l.trace_id = :trace")
            params["trace"] = trace_id

        if ref:
            cond.append("l.ref = :ref")
            params["ref"] = ref

        sql = f"""
            SELECT
                l.id,
                l.occurred_at,
                l.created_at,
                l.reason,
                l.ref,
                l.ref_line,
                l.trace_id,
                l.warehouse_id,
                l.item_id,
                lo.lot_code AS batch_code,
                l.lot_id,
                l.delta,
                l.after_qty,
                CASE
                    WHEN l.reason IN ('RECEIPT','INBOUND','INBOUND_RECEIPT') THEN 'INBOUND'
                    WHEN l.reason IN ('SHIP','SHIPMENT','OUTBOUND_SHIP','OUTBOUND_COMMIT') THEN 'OUTBOUND'
                    WHEN l.reason IN ('COUNT','STOCK_COUNT','INVENTORY_COUNT') THEN 'COUNT'
                    WHEN l.reason IN ('ADJUST','ADJUSTMENT','MANUAL_ADJUST') THEN 'ADJUST'
                    WHEN l.reason IN ('RETURN','RMA','INBOUND_RETURN') THEN 'RETURN'
                    ELSE 'UNKNOWN'
                END AS movement_type
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE {" AND ".join(cond)}
            ORDER BY l.occurred_at ASC, l.id ASC;
        """

        rs = (await session.execute(text(sql), params)).mappings().all()


        out = [dict(r) for r in rs]

        # Phase M-4 governance：lot_code 正名；batch_code 兼容字段

        for x in out:

            bc = x.get("batch_code")

            x["lot_code"] = bc

        return out
