# app/shipping_assist/pricing/bindings/summary_routes.py
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.shipping_assist.permissions import check_config_perm
from app.shipping_assist.pricing.bindings.contracts import (
    ActiveCarrierOut,
    WarehouseActiveCarriersOut,
    WarehouseActiveCarriersSummaryOut,
)

router = APIRouter()


@router.get(
    "/warehouses/active-carriers/summary",
    response_model=WarehouseActiveCarriersSummaryOut,
    name="pricing_list_warehouses_active_carriers_summary",
)
async def list_warehouses_active_carriers_summary(
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseActiveCarriersSummaryOut:
    """
    bindings 辅助汇总接口（消除 N+1）

    刚性契约口径：
    - 只返回当前真正正在服务的快递公司：
      1) wsp.active = true
      2) sp.active = true
      3) wsp.active_template_id IS NOT NULL
      4) effective_from 为空或已到生效时间
    - 不做推荐策略，不做 fallback
    - 排序仅用于展示稳定：
      warehouse_id ASC, wsp.priority ASC, sp.priority ASC, sp.id ASC
    """
    check_config_perm(db, current_user, ["config.store.read"])

    sql = text(
        """
        SELECT
          wsp.warehouse_id,
          sp.id   AS provider_id,
          sp.code AS provider_code,
          sp.name AS provider_name,
          wsp.priority AS wsp_priority,
          sp.priority  AS sp_priority
        FROM warehouse_shipping_providers AS wsp
        JOIN shipping_providers AS sp
          ON sp.id = wsp.shipping_provider_id
        WHERE wsp.active = true
          AND sp.active = true
          AND wsp.active_template_id IS NOT NULL
          AND (wsp.effective_from IS NULL OR wsp.effective_from <= now())
        ORDER BY wsp.warehouse_id ASC, wsp.priority ASC, sp.priority ASC, sp.id ASC
        """
    )

    rows = (await session.execute(sql)).mappings().all()

    by_wid: Dict[int, list[ActiveCarrierOut]] = {}
    for r in rows:
        wid = int(r["warehouse_id"])
        by_wid.setdefault(wid, []).append(
            ActiveCarrierOut(
                provider_id=int(r["provider_id"]),
                code=r.get("provider_code"),
                name=str(r["provider_name"]),
                priority=int(r.get("wsp_priority") or 0),
            )
        )

    data = [
        WarehouseActiveCarriersOut(
            warehouse_id=wid,
            active_carriers=carriers,
            active_carriers_count=len(carriers),
        )
        for wid, carriers in sorted(by_wid.items(), key=lambda x: x[0])
    ]

    return WarehouseActiveCarriersSummaryOut(ok=True, data=data)
