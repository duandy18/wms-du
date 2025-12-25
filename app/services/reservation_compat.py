# app/services/reservation_compat.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.store_service import StoreService


async def reserve_plan_only(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: List[Dict[str, Any]],
    warehouse_id: Optional[int] = None,
    reservation_error_type,
) -> Dict[str, Any]:
    """
    兼容旧测试用的“纯计划版” Reserve：
    - 只根据 store_warehouse 绑定和显式 warehouse_id 计算计划；
    - 不写 reservations / reservation_lines / stock_ledger；
    - 不扣库存；
    - 幂等（同样输入返回相同结果）；
    - 无默认仓且未传 warehouse_id 时抛 ReservationError。
    """
    wh_id: Optional[int] = warehouse_id
    if wh_id is None:
        wh_id = await StoreService.resolve_default_warehouse_for_platform_shop(
            session,
            platform=platform,
            shop_id=shop_id,
        )

    if wh_id is None:
        raise reservation_error_type(
            f"No warehouse specified or configured for {platform}/{shop_id}"
        )

    plan: List[Dict[str, Any]] = []
    for ln in lines or []:
        item_id = int(ln["item_id"])
        qty = int(ln["qty"])
        plan.append(
            {
                "warehouse_id": wh_id,
                "item_id": item_id,
                "qty": qty,
                "batch_id": None,
            }
        )

    return {
        "status": "OK",
        "warehouse_id": wh_id,
        "plan": plan,
    }
