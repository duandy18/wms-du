# app/services/outbound_metrics_v2.py

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import (
    FefoRiskMetricsResponse,
    OutboundFailuresMetricsResponse,
    OutboundMetricsV2,
    OutboundRangeMetricsResponse,
    OutboundShopMetricsResponse,
    OutboundWarehouseMetricsResponse,
)

from app.services.outbound_metrics_v2_common import UTC
from app.services.outbound_metrics_v2_day import load_day as _load_day
from app.services.outbound_metrics_v2_failures import load_failures as _load_failures
from app.services.outbound_metrics_v2_fefo_risk import load_fefo_risk as _load_fefo_risk
from app.services.outbound_metrics_v2_range import load_range as _load_range
from app.services.outbound_metrics_v2_shop import load_by_shop as _load_by_shop
from app.services.outbound_metrics_v2_warehouse import load_by_warehouse as _load_by_warehouse


class OutboundMetricsV2Service:
    """
    出库指标 v2 统一服务：
    - 单日大盘          (load_day)
    - 多日趋势          (load_range)
    - 仓库维度          (load_by_warehouse)
    - 失败诊断          (load_failures)
    - FEFO 风险监控     (load_fefo_risk)
    - 店铺维度          (load_by_shop)
    """

    async def load_day(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundMetricsV2:
        return await _load_day(session=session, day=day, platform=platform)

    async def load_range(
        self,
        session: AsyncSession,
        platform: str,
        days: int,
        end_day: Optional[date] = None,
    ) -> OutboundRangeMetricsResponse:
        return await _load_range(session=session, platform=platform, days=days, end_day=end_day)

    async def load_by_warehouse(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundWarehouseMetricsResponse:
        return await _load_by_warehouse(session=session, day=day, platform=platform)

    async def load_failures(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundFailuresMetricsResponse:
        return await _load_failures(session=session, day=day, platform=platform)

    async def load_fefo_risk(
        self,
        session: AsyncSession,
        days: int = 7,
    ) -> FefoRiskMetricsResponse:
        return await _load_fefo_risk(session=session, days=days)

    async def load_by_shop(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundShopMetricsResponse:
        return await _load_by_shop(session=session, day=day, platform=platform)


__all__ = [
    "OutboundMetricsV2Service",
    "UTC",
]
