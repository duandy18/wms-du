# app/services/inventory_autoheal_execute.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.inventory_autoheal_service import InventoryAutoHealService
from app.services.stock_service import StockService


class InventoryAutoHealExecutor:
    """
    Auto-Heal Executor（自动校正执行器）
    -------------------------------------
    把 auto-heal 建议真正执行为 ledger 行与 stocks 变更。

    功能：
    - dry_run=True: 提供即将执行的操作（不落库）
    - dry_run=False: 自动执行 adjust()，落库存 + ledger

    ✅ Scope 第一阶段：
    - 默认只在 PROD 口径执行，避免把训练口径混进运营数据
    """

    @staticmethod
    async def execute(
        session: AsyncSession,
        *,
        cut: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        suggestions = (await InventoryAutoHealService.suggest(session, cut=cut))["suggestions"]

        if dry_run:
            return {
                "dry_run": True,
                "count": len(suggestions),
                "operations": suggestions,
            }

        # 真执行校正
        stocksvc = StockService()
        ts = datetime.now(timezone.utc)
        executed = []

        for s in suggestions:
            wh = s["warehouse_id"]
            item = s["item_id"]
            batch = s["batch_code"]
            delta = s["diff"]

            ref = f"autoheal:{ts.isoformat()}"
            reason = MovementType.ADJUST

            adj = await stocksvc.adjust(
                session=session,
                scope="PROD",
                item_id=item,
                warehouse_id=wh,
                batch_code=batch,
                delta=delta,
                reason=reason,
                ref=ref,
                ref_line=1,
                occurred_at=ts,
                trace_id=f"autoheal-{ts.timestamp()}",
            )
            executed.append(adj)

        return {
            "dry_run": False,
            "executed": executed,
            "count": len(executed),
        }
