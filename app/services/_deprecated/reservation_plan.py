# app/services/reservation_plan.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.reservation_service import ReservationError, ReservationService


async def reserve_plan(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: List[Dict[str, Any]],
    warehouse_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    仅返回锁量计划（按仓维度，不启用批次），不落库、不写账：
      - 解析默认仓（若未显式传入）；
      - 严格校验每条行：必须含 item_id/qty 且为正整数；
      - 返回 plan: [{item_id, qty, warehouse_id, ref_line, batch_id=None}, ...]
    """
    _, wh = await ReservationService.ensure_store_and_warehouse(
        session, platform=platform, shop_id=shop_id, warehouse_id=warehouse_id
    )

    plan_rows = []
    for idx, raw in enumerate(lines or [], start=1):
        try:
            item_id = int(raw["item_id"])
            qty = int(raw["qty"])
        except (KeyError, ValueError, TypeError) as e:
            raise ReservationError(f"INVALID_LINE_DATA[{idx}]: {e}") from e
        if item_id <= 0 or qty <= 0:
            raise ReservationError(f"INVALID_LINE_VALUE[{idx}]: item_id/qty must be positive.")

        plan_rows.append(
            {
                "item_id": item_id,
                "qty": qty,
                "warehouse_id": wh,
                "ref_line": raw.get("ref_line", idx),
                "batch_id": None,  # 扩展位：未来支持批次/FEFO 时启用
            }
        )

    return {"status": "OK", "warehouse_id": wh, "plan": plan_rows}
