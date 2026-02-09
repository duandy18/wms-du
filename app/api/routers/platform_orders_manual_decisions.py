# app/api/routers/platform_orders_manual_decisions.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.platform_order_resolve_service import norm_platform
from app.api.routers.platform_orders_manual_decisions_schemas import ManualDecisionOrdersOut

router = APIRouter(tags=["platform-orders"])


def _as_int(v: Any) -> Optional[int]:
    try:
        n = int(v)
        return n
    except Exception:
        return None


@router.get(
    "/platform-orders/manual-decisions/latest",
    response_model=ManualDecisionOrdersOut,
    summary="读取最近的人工救火批次（platform_order_manual_decisions），用于治理证据回流（不写绑定）",
)
async def list_latest_manual_decisions(
    platform: str = Query(..., description="平台（如 DEMO/PDD/TB），大小写不敏感"),
    store_id: int = Query(..., ge=1, description="内部店铺 store_id（stores.id）"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ManualDecisionOrdersOut:
    plat = norm_platform(platform)
    sid = int(store_id)

    # 1) 拉出最近 batch 列表（按 batch 最新 created_at 排序）
    batch_rows = (
        await session.execute(
            text(
                """
                SELECT batch_id, MAX(created_at) AS latest_created_at
                  FROM platform_order_manual_decisions
                 WHERE platform = :platform
                   AND store_id = :store_id
                 GROUP BY batch_id
                 ORDER BY latest_created_at DESC
                 LIMIT :limit OFFSET :offset
                """
            ),
            {"platform": plat, "store_id": sid, "limit": int(limit), "offset": int(offset)},
        )
    ).mappings().all()

    # total = batch 总数
    total_row = (
        await session.execute(
            text(
                """
                SELECT COUNT(DISTINCT batch_id) AS n
                  FROM platform_order_manual_decisions
                 WHERE platform = :platform
                   AND store_id = :store_id
                """
            ),
            {"platform": plat, "store_id": sid},
        )
    ).mappings().first()
    total = int(total_row.get("n") or 0) if total_row else 0

    batch_ids: List[str] = [str(r.get("batch_id")) for r in batch_rows if r.get("batch_id") is not None]
    if not batch_ids:
        return ManualDecisionOrdersOut(items=[], total=total, limit=int(limit), offset=int(offset))

    # 2) 拉 batch 明细
    fact_rows = (
        await session.execute(
            text(
                """
                SELECT
                    batch_id,
                    platform, store_id, ext_order_no, order_id,
                    line_key, line_no, platform_sku_id, fact_qty,
                    item_id, qty, note,
                    manual_reason, risk_flags,
                    created_at
                  FROM platform_order_manual_decisions
                 WHERE batch_id = ANY(:batch_ids)
                 ORDER BY created_at DESC, id ASC
                """
            ),
            {"batch_ids": batch_ids},
        )
    ).mappings().all()

    # 3) 预取 orders.shop_id（保持输出兼容）
    order_ids: List[int] = []
    for r in fact_rows:
        oid = _as_int(r.get("order_id"))
        if oid is not None:
            order_ids.append(oid)
    order_ids = sorted(set(order_ids))

    order_shop_map: Dict[int, str] = {}
    if order_ids:
        o_rows = (
            await session.execute(
                text(
                    """
                    SELECT id, shop_id
                      FROM orders
                     WHERE id = ANY(:order_ids)
                    """
                ),
                {"order_ids": order_ids},
            )
        ).mappings().all()
        for o in o_rows:
            oid = _as_int(o.get("id"))
            if oid is None:
                continue
            order_shop_map[oid] = str(o.get("shop_id") or "")

    # 4) batch -> latest_created_at
    batch_latest_map: Dict[str, Any] = {}
    for br in batch_rows:
        bid = str(br.get("batch_id"))
        batch_latest_map[bid] = br.get("latest_created_at")

    # 5) 组装输出（按 batch 聚合）
    grouped: Dict[str, Dict[str, Any]] = {}
    for r in fact_rows:
        bid = str(r.get("batch_id"))
        if bid not in grouped:
            oid = _as_int(r.get("order_id"))  # may be None
            shop_id = order_shop_map.get(oid, "") if oid is not None else ""
            ext = str(r.get("ext_order_no") or "")
            p = str(r.get("platform") or plat)

            grouped[bid] = {
                "batch_id": bid,
                "created_at": batch_latest_map.get(bid) or r.get("created_at"),
                "order_id": int(oid) if oid is not None else 0,
                "platform": p,
                "shop_id": shop_id,
                "ext_order_no": ext,
                "ref": f"ORD:{p}:{shop_id}:{ext}",
                "store_id": int(r.get("store_id") or sid),
                "manual_reason": r.get("manual_reason") if isinstance(r.get("manual_reason"), str) else None,
                "risk_flags": [],
                "manual_decisions": [],
            }

        # risk_flags：取并集
        rf = r.get("risk_flags")
        if isinstance(rf, list):
            for x in rf:
                if isinstance(x, str) and x not in grouped[bid]["risk_flags"]:
                    grouped[bid]["risk_flags"].append(x)

        # decision 明细：每行一条
        grouped[bid]["manual_decisions"].append(
            {
                "line_key": r.get("line_key"),
                "line_no": r.get("line_no"),
                "platform_sku_id": r.get("platform_sku_id"),
                "fact_qty": r.get("fact_qty"),
                "item_id": r.get("item_id"),
                "qty": r.get("qty"),
                "note": r.get("note"),
            }
        )

    # 6) 保持顺序：按 batch_rows 的顺序输出
    items: List[Dict[str, Any]] = []
    for br in batch_rows:
        bid = str(br.get("batch_id"))
        if bid in grouped:
            items.append(grouped[bid])

    return ManualDecisionOrdersOut(items=items, total=total, limit=int(limit), offset=int(offset))
