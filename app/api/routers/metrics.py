# app/api/routers/metrics.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.metrics_alerts import AlertsResponse
from app.schemas.metrics_outbound_v2 import (
    FefoRiskMetricsResponse,
    OutboundFailuresMetricsResponse,
    OutboundMetricsV2,
    OutboundRangeMetricsResponse,
    OutboundShopMetricsResponse,
    OutboundWarehouseMetricsResponse,
)
from app.schemas.metrics_shipping_quote import ShippingQuoteFailuresMetricsResponse
from app.services.metrics_alerts import load_alerts
from app.services.outbound_metrics_v2 import OutboundMetricsV2Service
from app.services.shipping_quote_metrics_failures import load_shipping_quote_failures

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _today_utc_date() -> date:
    return datetime.utcnow().date()


# ---------------------------------------------------------
# 0) Alerts /alerts/today
# ---------------------------------------------------------


@router.get("/alerts/today", response_model=AlertsResponse)
async def get_alerts_today(
    platform: Optional[str] = Query(None, description="平台标识，如 PDD / TB / JD；不传则只返回报价域告警"),
    day: Optional[date] = Query(None, description="UTC 日期 (YYYY-MM-DD)，默认今天"),
    test_mode: bool = Query(False, description="测试模式：降低阈值，便于验收告警结构"),
    session: AsyncSession = Depends(get_session),
) -> AlertsResponse:
    """
    可报警面板（Phase 4.3）：
    - OUTBOUND：基于 SHIP_CONFIRM_REJECT 的 error_code（需要 platform）
    - SHIPPING_QUOTE：基于 QUOTE_*_REJECT 的 error_code
    """
    return await load_alerts(session=session, platform=platform, day=day, test_mode=test_mode)


# ---------------------------------------------------------
# 1) 单日大盘（today + by-day/{day}）
# ---------------------------------------------------------


@router.get("/outbound/today", response_model=OutboundMetricsV2)
async def get_outbound_metrics_today(
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    session: AsyncSession = Depends(get_session),
) -> OutboundMetricsV2:
    """
    单平台今日出库指标大盘（v2 结构）
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_day(session=session, day=_today_utc_date(), platform=platform)


@router.get("/outbound/by-day/{day}", response_model=OutboundMetricsV2)
async def get_outbound_metrics_by_day(
    day: date = Path(..., description="UTC 日期 (YYYY-MM-DD)"),
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    session: AsyncSession = Depends(get_session),
) -> OutboundMetricsV2:
    """
    单平台指定日期出库指标大盘（v2 结构）
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_day(session=session, day=day, platform=platform)


# ---------------------------------------------------------
# 2) 多日趋势 /range
# ---------------------------------------------------------


@router.get("/outbound/range", response_model=OutboundRangeMetricsResponse)
async def get_outbound_metrics_range(
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    days: int = Query(7, ge=1, le=60, description="向前追溯的天数（默认 7 天）"),
    end_day: Optional[date] = Query(None, description="结束日期（默认今天，UTC）"),
    session: AsyncSession = Depends(get_session),
) -> OutboundRangeMetricsResponse:
    """
    最近 N 天出库趋势（按天汇总成功率 / FEFO 命中率 / fallback 比例）。
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_range(
        session=session,
        platform=platform,
        days=days,
        end_day=end_day,
    )


# ---------------------------------------------------------
# 3) 仓库维度 /by-warehouse
# ---------------------------------------------------------


@router.get(
    "/outbound/by-warehouse",
    response_model=OutboundWarehouseMetricsResponse,
)
async def get_outbound_metrics_by_warehouse(
    day: date = Query(..., description="日期 (YYYY-MM-DD, UTC)"),
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    session: AsyncSession = Depends(get_session),
) -> OutboundWarehouseMetricsResponse:
    """
    按仓库拆分出库表现。
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_by_warehouse(session=session, day=day, platform=platform)


# ---------------------------------------------------------
# 4) 出库失败诊断 /failures
# ---------------------------------------------------------


@router.get(
    "/outbound/failures",
    response_model=OutboundFailuresMetricsResponse,
)
async def get_outbound_failures(
    day: date = Query(..., description="日期 (YYYY-MM-DD, UTC)"),
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    session: AsyncSession = Depends(get_session),
) -> OutboundFailuresMetricsResponse:
    """
    出库失败统计：routing/pick/ship/inventory 等失败点汇总 + 明细。
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_failures(session=session, day=day, platform=platform)


# ---------------------------------------------------------
# 4.1) Shipping Quote 失败诊断 /shipping-quote/failures
# ---------------------------------------------------------


@router.get(
    "/shipping-quote/failures",
    response_model=ShippingQuoteFailuresMetricsResponse,
)
async def get_shipping_quote_failures(
    day: date = Query(..., description="日期 (YYYY-MM-DD, UTC)"),
    limit: int = Query(200, ge=1, le=2000, description="返回明细条数上限（默认 200）"),
    session: AsyncSession = Depends(get_session),
) -> ShippingQuoteFailuresMetricsResponse:
    """
    Shipping Quote 失败统计：calc/recommend 的 reject 按 error_code 聚合 + 明细。
    """
    return await load_shipping_quote_failures(session=session, day=day, limit=limit)


# ---------------------------------------------------------
# 5) FEFO 风险监控 /fefo-risk
# ---------------------------------------------------------


@router.get("/fefo-risk", response_model=FefoRiskMetricsResponse)
async def get_fefo_risk_metrics(
    days: int = Query(7, ge=1, le=60, description="回看 FEFO 命中率的天数（默认 7 天）"),
    session: AsyncSession = Depends(get_session),
) -> FefoRiskMetricsResponse:
    """
    FEFO 风险面板：近期临期批次 + FEFO 命中率 + 风险评分。
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_fefo_risk(session=session, days=days)


# ---------------------------------------------------------
# 6) 店铺维度 /by-shop
# ---------------------------------------------------------


@router.get(
    "/outbound/by-shop",
    response_model=OutboundShopMetricsResponse,
)
async def get_outbound_metrics_by_shop(
    day: date = Query(..., description="日期 (YYYY-MM-DD, UTC)"),
    platform: str = Query(..., description="平台标识，如 PDD / TB / JD"),
    session: AsyncSession = Depends(get_session),
) -> OutboundShopMetricsResponse:
    """
    按店铺拆分出库表现。
    """
    svc = OutboundMetricsV2Service()
    return await svc.load_by_shop(session=session, day=day, platform=platform)
