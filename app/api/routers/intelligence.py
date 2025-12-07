# app/api/routers/intelligence.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.batch_ageing_service import BatchAgeingService
from app.services.inventory_anomaly_service import InventoryAnomalyService
from app.services.inventory_autoheal_service import InventoryAutoHealService
from app.services.inventory_insights_service import InventoryInsightsService
from app.services.inventory_predict_service import InventoryPredictService

router = APIRouter(prefix="/inventory/intelligence", tags=["inventory_intelligence"])


@router.get("/insights")
async def get_insights(
    session: AsyncSession = Depends(get_session),
):
    """
    全局库存洞察：
    - inventory_health_score
    - inventory_accuracy_score
    - snapshot_accuracy_score
    - batch_activity_30days
    - batch_risk_score
    - warehouse_efficiency
    """
    svc = InventoryInsightsService()
    insights = await svc.insights(session)
    return {"ok": True, "insights": insights}


@router.get("/anomaly")
async def detect_anomaly(
    cut: str,
    session: AsyncSession = Depends(get_session),
):
    """
    库存异常检测：
    - ledger vs stocks/snapshot 不一致记录
    """
    svc = InventoryAnomalyService()
    anomaly = await svc.detect(session, cut=cut)
    return {"ok": True, "anomaly": anomaly}


@router.get("/ageing")
async def detect_ageing(
    within_days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """
    批次老化检测：
    - 找出在 within_days 天内即将到期的批次
    """
    svc = BatchAgeingService()
    ageing = await svc.detect(session, within_days=within_days)
    return {"ok": True, "ageing": ageing}


@router.get("/autoheal")
async def autoheal(
    cut: str,
    session: AsyncSession = Depends(get_session),
):
    """
    自动校正建议（不执行）：
    - 基于 ledger_cut 与 stocks 差异给出调整建议列表
    """
    svc = InventoryAutoHealService()
    autoheal = await svc.suggest(session, cut=cut)
    return {"ok": True, "autoheal": autoheal}


@router.get("/predict")
async def predict(
    warehouse_id: int,
    item_id: int,
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    """
    简单库存预测：
    - 基于最近 30 天出库趋势，估算未来 days 天库存量
    """
    svc = InventoryPredictService()
    predict = await svc.predict(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        days=days,
    )
    return {"ok": True, "predict": predict}
