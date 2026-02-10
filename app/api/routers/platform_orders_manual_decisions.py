# app/api/routers/platform_orders_manual_decisions.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.services.platform_order_resolve_service import norm_platform
from app.api.routers.platform_orders_manual_decisions_schemas import ManualDecisionOrdersOut

router = APIRouter(tags=["platform-orders"])


def _as_int(v: Any) -> Optional[int]:
    try:
        n = int(v)
        return n
    except Exception:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _load_shop_id_by_store_id(session: AsyncSession, *, platform: str, store_id: int) -> Optional[str]:
    plat = norm_platform(platform)
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :sid
                       AND platform = :p
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "p": plat},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    v = row.get("shop_id")
    s = str(v).strip() if v is not None else ""
    return s or None


class ManualBindMerchantCodeIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32, description="平台（DEMO/PDD/TB），大小写不敏感")
    store_id: int = Field(..., ge=1, description="内部店铺 store_id（stores.id）")
    filled_code: str = Field(..., min_length=1, max_length=128, description="填写码（商家规格编码 / filled_code）")
    fsku_id: int = Field(..., ge=1, description="目标 FSKU.id（必须为 published）")
    reason: Optional[str] = Field(None, max_length=500, description="绑定原因（可选）")


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
                    line_key, line_no,
                    filled_code,
                    fact_qty,
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
                "filled_code": r.get("filled_code"),
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


@router.post(
    "/platform-orders/manual-decisions/bind-merchant-code",
    summary="人工救火：将 filled_code 写入 merchant_code_fsku_bindings(current) → published FSKU（一次救火，后续自动解析）",
)
async def manual_bind_merchant_code(
    payload: ManualBindMerchantCodeIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    plat = norm_platform(payload.platform)
    store_id = int(payload.store_id)

    filled_code = (payload.filled_code or "").strip()
    if not filled_code:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="filled_code 不能为空",
                context={"platform": plat, "store_id": store_id},
            ),
        )

    shop_id = await _load_shop_id_by_store_id(session, platform=plat, store_id=store_id)
    if not shop_id:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="store_id 不存在或未绑定 shop_id",
                context={"platform": plat, "store_id": store_id},
            ),
        )

    # 校验 FSKU 必须 published
    fsku_row = (
        await session.execute(
            text(
                """
                SELECT id, status
                  FROM fskus
                 WHERE id = :id
                 LIMIT 1
                """
            ),
            {"id": int(payload.fsku_id)},
        )
    ).mappings().first()

    if not fsku_row or fsku_row.get("id") is None:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="FSKU 不存在",
                context={"platform": plat, "store_id": store_id, "fsku_id": int(payload.fsku_id)},
            ),
        )

    st = str(fsku_row.get("status") or "")
    if st != "published":
        raise HTTPException(
            status_code=409,
            detail=make_problem(
                status_code=409,
                error_code="conflict",
                message="仅 published FSKU 允许绑定（避免草稿/退休被订单引用）",
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "shop_id": shop_id,
                    "fsku_id": int(payload.fsku_id),
                    "fsku_status": st,
                },
            ),
        )

    now = _utc_now()
    reason = (payload.reason or "").strip() or "manual bind"

    # 关闭旧 current + 插入新 current（依赖 partial unique index 做最终裁决）
    await session.execute(
        text(
            """
            UPDATE merchant_code_fsku_bindings
               SET effective_to = :now
             WHERE platform = :p
               AND shop_id = :shop_id
               AND merchant_code = :code
               AND effective_to IS NULL
            """
        ),
        {"now": now, "p": plat, "shop_id": shop_id, "code": filled_code},
    )

    await session.execute(
        text(
            """
            INSERT INTO merchant_code_fsku_bindings(
              platform, shop_id, merchant_code,
              fsku_id, effective_from, effective_to, reason, created_at
            )
            VALUES (
              :p, :shop_id, :code,
              :fsku_id, :now, NULL, :reason, :now
            )
            """
        ),
        {"p": plat, "shop_id": shop_id, "code": filled_code, "fsku_id": int(payload.fsku_id), "now": now, "reason": reason},
    )

    await session.commit()

    return {
        "ok": True,
        "data": {
            "platform": plat,
            "store_id": store_id,
            "shop_id": shop_id,
            "merchant_code": filled_code,
            "fsku_id": int(payload.fsku_id),
            "reason": reason,
            "effective_from": now,
        },
        "next_actions": [
            {
                "action": "re_ingest_or_replay",
                "label": "重新接入/回放该订单（后续同 filled_code 将自动解析）",
            }
        ],
    }
