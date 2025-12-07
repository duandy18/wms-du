# app/jobs/snapshot_pipeline.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_event
from app.services.inventory_anomaly_service import InventoryAnomalyService
from app.services.snapshot_v3_service import SnapshotV3Service


class SnapshotPipeline:
    """
    Snapshot v3 自动化流水线：
      - 自动生成当日快照
      - 对账（ledger_cut vs snapshot_v3）
    """

    @staticmethod
    async def run(session: AsyncSession):
        now = datetime.now(timezone.utc)

        # 1) 生成 snapshot v3
        snap = await SnapshotV3Service.rebuild_snapshot_from_ledger(session, snapshot_date=now)

        # 2) 对账检查
        anomaly = await InventoryAnomalyService.detect(session, cut=now.isoformat())

        if anomaly["ledger_vs_snapshot"]:
            audit_event(
                session,
                source="snapshot_pipeline",
                kind="SNAPSHOT_ANOMALY",
                detail=anomaly,
            )

        return {"ok": True, "snapshot": snap}
