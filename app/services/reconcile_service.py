# app/services/reconcile_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.snapshot_run import run_snapshot
from app.services.stock_service import StockService


class ReconcileService:
    """
    盘点/对账服务（统一走 StockService，不直连 SQL）：
    - 不控事务；外层决定事务边界；
    - 结构化返回，纯业务字段；
    - 幂等与原子性由 StockService 内部的“ref + 行锁/唯一键”保障。

    Phase 3（本次）：
    - delta==0 也落一笔确认类台账（COUNT_CONFIRM），用于审计可追溯
    """

    def __init__(self, stock: StockService | None = None) -> None:
        self.stock = stock or StockService()

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        actual_qty: int,
        ref: str,
    ) -> Dict[str, Any]:
        on_hand = await self.stock.get_on_hand(
            session=session, item_id=item_id, location_id=location_id
        )
        delta = int(actual_qty) - int(on_hand)

        result: Dict[str, Any] = {
            "on_hand_before": on_hand,
            "actual": int(actual_qty),
            "delta": delta,
        }

        meta = {"sub_reason": "COUNT_ADJUST" if delta != 0 else "COUNT_CONFIRM"}
        if delta == 0:
            meta["allow_zero_delta_ledger"] = True

        # 无论 delta 是否为 0，都调用 adjust（delta==0 -> 只记账不改库存）
        adj = await self.stock.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref=ref,
            occurred_at=datetime.now(timezone.utc),
            meta=meta,
        )

        # 尾门：location 维度这里没法直接复用 verify_commit_three_books（它是 warehouse+batch 粒度）
        # 所以这里只保证：delta==0 不报错，且对外返回一致。
        # 三账一致性校验留给 warehouse+batch 的主链（scan count / adjust_impl）处理。
        result.update({"on_hand_after": adj.get("on_hand_after", on_hand + delta)})

        # 可选：如果你希望 reconcile 也刷新快照（通常不需要）
        _ = run_snapshot  # 保留引用，避免 lint 抱怨（当前不调用）

        return result
