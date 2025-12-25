# app/services/order_lifecycle_v2_service_impl.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_service import TraceService

from app.services.order_lifecycle_v2_build import (
    build_stages_from_events,
    inject_delivered_stage,
    summarize_stages,
)
from app.services.order_lifecycle_v2_types import LifecycleStage, LifecycleSummary


class OrderLifecycleV2Service:
    """
    v2 生命周期服务：统一基于 trace_id 推断（纯表驱动版）。

    本次扩展：
    - 通过 shipping_records(status=DELIVERED) 注入 delivered 阶段，
      使生命周期能够一直展示到“订单送达”。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._trace_service = TraceService(session)

    async def _load_delivered_info(self, trace_id: str) -> Tuple[Optional[datetime], Optional[str]]:
        sql = text(
            """
            SELECT delivery_time, order_ref
              FROM shipping_records
             WHERE trace_id = :tid
               AND status = 'DELIVERED'
               AND delivery_time IS NOT NULL
             ORDER BY delivery_time ASC, id ASC
             LIMIT 1
            """
        )
        res = await self.session.execute(sql, {"tid": trace_id})
        row = res.mappings().first()
        if not row:
            return None, None
        return row["delivery_time"], row["order_ref"]

    async def for_trace_id(self, trace_id: str) -> List[LifecycleStage]:
        result = await self._trace_service.get_trace(trace_id)
        stages = build_stages_from_events(result.events)

        delivered_ts, delivered_ref = await self._load_delivered_info(trace_id)
        if delivered_ts is not None:
            stages = inject_delivered_stage(stages, ts=delivered_ts, ref=delivered_ref)

        return stages

    async def for_trace_id_with_summary(
        self, trace_id: str
    ) -> Tuple[List[LifecycleStage], LifecycleSummary]:
        stages = await self.for_trace_id(trace_id)
        summary = summarize_stages(stages)
        return stages, summary

    async def for_trace_id_as_dicts(self, trace_id: str) -> Dict[str, Any]:
        stages, summary = await self.for_trace_id_with_summary(trace_id)
        return {
            "trace_id": trace_id,
            "stages": [asdict(s) for s in stages],
            "summary": asdict(summary),
        }
