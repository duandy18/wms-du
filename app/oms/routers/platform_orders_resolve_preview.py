# app/oms/routers/platform_orders_resolve_preview.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import make_problem
from app.db.deps import get_async_session as get_session
from app.oms.contracts.platform_orders_resolve_preview import (
    PlatformOrderResolvePreviewFactLineOut,
    PlatformOrderResolvePreviewIn,
    PlatformOrderResolvePreviewItemQtyOut,
    PlatformOrderResolvePreviewOut,
    PlatformOrderResolvePreviewResolvedLineOut,
)
from app.oms.repos.platform_orders_fact import (
    load_fact_lines_for_order,
    load_store_code_by_store_id,
)
from app.oms.services.platform_order_ingest_flow import PlatformOrderIngestFlow
from app.oms.services.platform_order_resolve_service import (
    load_items_brief,
    norm_platform,
)

router = APIRouter(tags=["platform-orders"])


def _preview_status(*, resolved_count: int, unresolved_count: int, item_qty_count: int) -> str:
    if item_qty_count > 0 and unresolved_count == 0:
        return "OK"
    if item_qty_count > 0 and unresolved_count > 0:
        return "PARTIAL"
    if resolved_count > 0 and unresolved_count == 0:
        return "OK"
    return "UNRESOLVED"


@router.post(
    "/platform-orders/resolve-preview",
    response_model=PlatformOrderResolvePreviewOut,
    summary="平台订单事实只读解析预览：读取 platform_order_lines 并展开到 FSKU/SKU，不建单",
)
async def preview_platform_order_resolve(
    payload: PlatformOrderResolvePreviewIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> PlatformOrderResolvePreviewOut:
    """
    只读解析预览。

    边界：
    - 读取 platform_order_lines；
    - 复用 resolver 展开 FSKU / item；
    - 返回 resolved / unresolved / item_qty_map；
    - 不写 platform_order_lines；
    - 不建 orders/order_items；
    - 不触碰 finance。
    """
    plat = norm_platform(payload.platform)
    store_id = int(payload.store_id)
    ext = str(payload.ext_order_no or "").strip()
    if not ext:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="ext_order_no 不能为空",
                context={"platform": plat, "store_id": store_id},
            ),
        )

    try:
        store_code = await load_store_code_by_store_id(session, store_id=store_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="store_id 不存在",
                context={"platform": plat, "store_id": store_id, "ext_order_no": ext},
            ),
        )

    fact_lines = await load_fact_lines_for_order(
        session,
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
    )

    if not fact_lines:
        return PlatformOrderResolvePreviewOut(
            status="NOT_FOUND",
            ref=f"ORD:{plat}:{store_code}:{ext}",
            platform=plat,
            store_id=store_id,
            ext_order_no=ext,
            facts_n=0,
            fact_lines=[],
            resolved=[],
            unresolved=[
                {
                    "reason": "FACTS_NOT_FOUND",
                    "hint": "未找到该订单的事实行（platform/store_id/ext_order_no）",
                }
            ],
            item_qty_map={},
            item_qty_items=[],
        )

    resolved_lines, unresolved, item_qty_map = await PlatformOrderIngestFlow.resolve_fact_lines(
        session,
        platform=plat,
        store_id=store_id,
        lines=fact_lines,
    )

    items_brief = await load_items_brief(
        session,
        item_ids=sorted(int(x) for x in item_qty_map.keys()),
    )

    item_qty_items = [
        PlatformOrderResolvePreviewItemQtyOut(
            item_id=int(item_id),
            qty=int(item_qty_map[item_id]),
            sku=(items_brief.get(int(item_id)) or {}).get("sku"),
            name=(items_brief.get(int(item_id)) or {}).get("name"),
        )
        for item_id in sorted(item_qty_map.keys())
    ]

    return PlatformOrderResolvePreviewOut(
        status=_preview_status(
            resolved_count=len(resolved_lines),
            unresolved_count=len(unresolved),
            item_qty_count=len(item_qty_map),
        ),
        ref=f"ORD:{plat}:{store_code}:{ext}",
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
        facts_n=len(fact_lines),
        fact_lines=[
            PlatformOrderResolvePreviewFactLineOut(
                line_no=int(line.get("line_no") or 0),
                line_key=str(line.get("line_key") or ""),
                locator_kind=line.get("locator_kind"),
                locator_value=line.get("locator_value"),
                filled_code=line.get("filled_code"),
                qty=int(line.get("qty") or 1),
                title=line.get("title"),
                spec=line.get("spec"),
                extras=line.get("extras") or {},
            )
            for line in fact_lines
        ],
        resolved=[
            PlatformOrderResolvePreviewResolvedLineOut(
                filled_code=str(line.filled_code),
                qty=int(line.qty),
                fsku_id=int(line.fsku_id),
                expanded_items=list(line.expanded_items or []),
            )
            for line in resolved_lines
        ],
        unresolved=list(unresolved or []),
        item_qty_map={str(int(k)): int(v) for k, v in item_qty_map.items()},
        item_qty_items=item_qty_items,
    )
