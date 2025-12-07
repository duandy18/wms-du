# app/jobs/inventory_guard.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_event
from app.services.batch_ageing_service import BatchAgeingService
from app.services.inventory_anomaly_service import InventoryAnomalyService
from app.services.inventory_autoheal_service import InventoryAutoHealService


class InventoryGuard:
    """
    Inventory Guard（库存守护者）
    -----------------------------
    自动后台检查库存健康：
      - 异常检测
      - 老化检测
      - 自动校正建议日志化
    """

    @staticmethod
    async def run(session: AsyncSession):
        now = datetime.now(timezone.utc).isoformat()

        # 1) 检查库存异常
        anomaly = await InventoryAnomalyService.detect(session, cut=now)
        if anomaly["ledger_vs_stocks"] or anomaly["ledger_vs_snapshot"]:
            audit_event(
                session,
                source="inventory_guard",
                kind="INVENTORY_ANOMALY",
                detail=anomaly,
            )

        # 2) 检查批次老化
        ageing = await BatchAgeingService.detect(session)
        if ageing:
            audit_event(
                session,
                source="inventory_guard",
                kind="BATCH_AGEING",
                detail={"count": len(ageing)},
            )

        # 3) 校正建议（但不执行）
        heal = await InventoryAutoHealService.suggest(session, cut=now)
        if heal["count"] > 0:
            audit_event(
                session,
                source="inventory_guard",
                kind="AUTOHEAL_SUGGEST",
                detail=heal,
            )

        return {"ok": True}
