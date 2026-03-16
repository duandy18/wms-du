# app/services/order_lifecycle_v2_service_impl.py
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_service import TraceService

from app.services.order_lifecycle_v2_build import (
    build_stages_from_events,
    summarize_stages,
)
from app.services.order_lifecycle_v2_types import LifecycleStage, LifecycleSummary


class OrderLifecycleV2Service:
    """
    v2 生命周期服务：统一基于 trace_id 推断（纯表驱动版）。

    当前终态：
    - 生命周期在“发运完成（shipped）”处收口；
    - 系统内不再基于 shipping_records / transport 侧状态字段注入 delivered；
    - 物流后续状态应由平台商铺 API / 平台事件获取，而不是由本地台账承担真相。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._trace_service = TraceService(session)

    async def for_trace_id(self, trace_id: str) -> List[LifecycleStage]:
        result = await self._trace_service.get_trace(trace_id)
        stages = build_stages_from_events(result.events)
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
