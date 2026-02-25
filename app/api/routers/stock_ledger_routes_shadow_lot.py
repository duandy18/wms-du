# app/api/routers/stock_ledger_routes_shadow_lot.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.routers.stock_ledger_helpers import normalize_time_range
from app.db.session import get_session
from app.schemas.stock_ledger import LedgerQuery
from app.schemas.stock_ledger_lot_shadow import LotShadowReconcileOut
from app.services.lot_shadow_reconcile_service import LotShadowReconcileService


def register(router: APIRouter) -> None:
    @router.post("/shadow-reconcile-lot", response_model=LotShadowReconcileOut)
    async def shadow_reconcile_lot(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LotShadowReconcileOut:
        """
        Phase 4A-2a / Step C:
        lot 维度影子对账（只读验证，不改 stocks 槽位）

        最小约束（避免全库扫）：
        - 必须指定 warehouse_id + item_id
        - 时间窗使用 normalize_time_range（<=90 天）
        - 可选 batch_code / lot_id 进一步缩小范围
        """
        if payload.warehouse_id is None or payload.item_id is None:
            raise HTTPException(status_code=400, detail="shadow-reconcile-lot 必须指定 warehouse_id + item_id。")

        # 对齐你现有查询行为：batch_code 先归一（None/空串/'None' -> None）
        norm_bc = normalize_optional_batch_code(getattr(payload, "batch_code", None))
        if getattr(payload, "batch_code", None) != norm_bc:
            payload = payload.model_copy(update={"batch_code": norm_bc})

        time_from, time_to = normalize_time_range(payload)

        data = await LotShadowReconcileService.reconcile(
            session,
            warehouse_id=int(payload.warehouse_id),
            item_id=int(payload.item_id),
            time_from=time_from,
            time_to=time_to,
            batch_code=getattr(payload, "batch_code", None),
            lot_id=getattr(payload, "lot_id", None),
        )

        return LotShadowReconcileOut.model_validate(data)
