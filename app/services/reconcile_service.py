# app/services/reconcile_service.py
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.stock_helpers import (
    ensure_item,
    get_current_qty,
)


class ReconcileService:
    """
    v1.0 盘点策略（最小且稳）：
      1) 基准只用 stocks（本进程入库/出库已维护一致性）
      2) 应用差异：盘盈 → inbound 到 CC-ADJ-YYYYMMDD；盘亏 → FEFO（允许过期优先）
      3) 盘后数量从 stocks 再读（权威值）
    """

    @staticmethod
    async def reconcile_inventory(
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        counted_qty: float,
        apply: bool = True,
        ref: str | None = None,
    ) -> dict:
        # 1) 外键兜底：确保最小域存在
        await ensure_item(session, item_id=item_id)

        # 2) 基准：账面 stocks（与 v1.0 正式口径一致）
        before = float(await get_current_qty(session, item_id=item_id, location_id=location_id))

        diff = float(counted_qty) - before
        result: dict[str, Any] = {
            "item_id": item_id,
            "location_id": location_id,
            "before_qty": before,
            "counted_qty": float(counted_qty),
            "diff": float(diff),
            "applied": bool(apply),
            "after_qty": before if not apply else None,
            "moves": [],
        }

        # 无需动作
        if abs(diff) < 1e-12:
            result["after_qty"] = before
            return result

        # 仅预估
        if not apply:
            result["moves"] = [("CYCLE_COUNT_UP" if diff > 0 else "CYCLE_COUNT_DOWN", float(diff))]
            result["after_qty"] = float(counted_qty)
            return result

        # 3) 应用差异
        if diff > 0:
            # 盘盈：入库到“当日调整批次”（可观测、可回滚）
            batch_code = f"CC-ADJ-{date.today():%Y%m%d}"
            adj = await InventoryAdjust.inbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(diff),
                reason="CYCLE_COUNT_UP",
                ref=ref or "CC-UP",
                batch_code=batch_code,
                production_date=date.today(),
                expiry_date=None,
            )
            result["moves"] = adj.get("batch_moves", [])
        else:
            # 盘亏：FEFO 下调（先过期，再近效，最后无效期）
            fefo = await InventoryAdjust.fefo_outbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(diff),  # 负数
                reason="CYCLE_COUNT_DOWN",
                ref=ref or "CC-DOWN",
                allow_expired=True,
            )
            result["moves"] = fefo.get("batch_moves", [])

        # 4) 盘后数量：从 stocks 再读权威值
        result["after_qty"] = float(await get_current_qty(session, item_id=item_id, location_id=location_id))
        return result
