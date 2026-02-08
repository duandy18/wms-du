# app/api/routers/platform_orders_replay.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, constr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.platform_order_resolve_service import (
    load_items_brief,
    norm_platform,
    resolve_platform_lines_to_items,
)

# ✅ 复用 ingest 的履约快照读取逻辑（保持合同一致）
from app.api.routers.platform_orders_ingest_helpers import load_order_fulfillment_brief

router = APIRouter(tags=["platform-orders"])


class PlatformOrderReplayIn(BaseModel):
    """
    平台订单事实重放解码（内部治理接口）：

    ✅ 规则：外来的叫 shop，内部的叫 store。
    - 入参只接收 store_id（stores.id）
    - 读取 platform_order_lines 事实行
    - 复用现有 resolver + OrderService.ingest 主线幂等
    """

    model_config = ConfigDict(extra="ignore")

    platform: constr(min_length=1, max_length=32)
    store_id: int = Field(..., ge=1)
    ext_order_no: constr(min_length=1)


class PlatformOrderReplayOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str

    platform: str
    store_id: int
    ext_order_no: str

    facts_n: int = 0
    resolved: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved: List[Dict[str, Any]] = Field(default_factory=list)

    # ✅ 与 ingest 合同对齐：直接透出履约状态与阻塞原因
    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None


async def _load_shop_id_by_store_id(session: AsyncSession, *, store_id: int) -> str:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :id
                     LIMIT 1
                    """
                ),
                {"id": int(store_id)},
            )
        )
        .mappings()
        .first()
    )
    shop = (row.get("shop_id") if row else None) if row is not None else None
    if not shop:
        raise LookupError(f"store not found: store_id={store_id}")
    return str(shop)


async def _load_fact_lines_for_order(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    line_no,
                    platform_sku_id,
                    qty,
                    title,
                    spec,
                    extras
                  FROM platform_order_lines
                 WHERE platform = :platform
                   AND store_id = :store_id
                   AND ext_order_no = :ext_order_no
                 ORDER BY line_no ASC
                """
            ),
            {"platform": str(platform), "store_id": int(store_id), "ext_order_no": str(ext_order_no)},
        )
    ).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "line_no": int(r.get("line_no") or 0),
                "platform_sku_id": (r.get("platform_sku_id") or None),
                "qty": int(r.get("qty") or 1),
                "title": r.get("title"),
                "spec": r.get("spec"),
                "extras": r.get("extras"),
            }
        )
    return out


def _build_items_payload_from_item_qty_map(
    *,
    item_qty_map: Dict[int, int],
    items_brief: Dict[int, Dict[str, Any]],
    store_id: int,
    source: str,
) -> List[Dict[str, Any]]:
    items_payload: List[Dict[str, Any]] = []
    for item_id in sorted(item_qty_map.keys()):
        need_qty = int(item_qty_map[item_id])
        brief = items_brief.get(item_id) or {}
        items_payload.append(
            {
                "item_id": int(item_id),
                "qty": need_qty,
                "sku_id": str(brief.get("sku") or ""),
                "title": str(brief.get("name") or ""),
                "extras": {"source": source, "store_id": store_id},
            }
        )
    return items_payload


@router.post(
    "/platform-orders/replay",
    response_model=PlatformOrderReplayOut,
    summary="平台订单事实重放解码：从 platform_order_lines 读取事实，复用 resolver + /orders ingest 主线幂等生成订单",
)
async def replay_platform_order(
    payload: PlatformOrderReplayIn = Body(...),
    session: AsyncSession = Depends(get_session),
):
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

    trace = new_trace("http:/platform-orders/replay")

    try:
        shop_id = await _load_shop_id_by_store_id(session, store_id=store_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="store_id 不存在",
                context={"platform": plat, "store_id": store_id, "ext_order_no": ext, "trace_id": trace.trace_id},
            ),
        )

    fact_lines = await _load_fact_lines_for_order(session, platform=plat, store_id=store_id, ext_order_no=ext)

    if not fact_lines:
        return PlatformOrderReplayOut(
            status="NOT_FOUND",
            id=None,
            ref=f"ORD:{plat}:{shop_id}:{ext}",
            platform=plat,
            store_id=store_id,
            ext_order_no=ext,
            facts_n=0,
            resolved=[],
            unresolved=[{"reason": "FACTS_NOT_FOUND", "hint": "未找到该订单的事实行（platform/store_id/ext_order_no）"}],
            fulfillment_status=None,
            blocked_reasons=None,
        )

    resolved_lines, unresolved, item_qty_map = await resolve_platform_lines_to_items(
        session,
        platform=plat,
        store_id=store_id,
        lines=fact_lines,
    )

    if not item_qty_map:
        return PlatformOrderReplayOut(
            status="UNRESOLVED",
            id=None,
            ref=f"ORD:{plat}:{shop_id}:{ext}",
            platform=plat,
            store_id=store_id,
            ext_order_no=ext,
            facts_n=len(fact_lines),
            resolved=[r.__dict__ for r in resolved_lines],
            unresolved=unresolved,
            fulfillment_status=None,
            blocked_reasons=None,
        )

    item_ids = sorted(item_qty_map.keys())
    items_brief = await load_items_brief(session, item_ids=item_ids)
    items_payload = _build_items_payload_from_item_qty_map(
        item_qty_map=item_qty_map,
        items_brief=items_brief,
        store_id=store_id,
        source="platform-orders/replay",
    )

    r = await OrderService.ingest(
        session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=None,
        buyer_name=None,
        buyer_phone=None,
        order_amount=0.0,
        pay_amount=0.0,
        items=items_payload,
        address=None,
        extras={"store_id": store_id, "source": "platform-orders/replay"},
        trace_id=trace.trace_id,
    )

    await session.commit()

    oid = int(r.get("id") or 0) if r.get("id") is not None else None
    ref = str(r.get("ref") or f"ORD:{plat}:{shop_id}:{ext}")

    fulfillment_status = None
    blocked_reasons = None
    if oid is not None:
        fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(session, order_id=oid)

    return PlatformOrderReplayOut(
        status=str(r.get("status") or "OK"),
        id=oid,
        ref=ref,
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
        facts_n=len(fact_lines),
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        fulfillment_status=fulfillment_status,
        blocked_reasons=blocked_reasons,
    )
