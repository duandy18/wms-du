# app/api/routers/platform_orders_ingest_routes.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow
from app.services.platform_order_resolve_service import (
    norm_platform,
    norm_shop_id,
    resolve_store_id,
)

from app.api.routers.platform_orders_ingest_helpers import (
    build_address,
    load_shop_id_by_store_id,
)
from app.api.routers.platform_orders_ingest_schemas import (
    PlatformOrderIngestIn,
    PlatformOrderIngestOut,
)

router = APIRouter(tags=["platform-orders"])


def _safe_preview(val: Any, max_len: int = 400) -> Optional[Any]:
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        s = str(val)
        return s if len(s) <= max_len else s[: max_len - 3] + "..."
    if isinstance(val, dict):
        return {k: _safe_preview(v, max_len=120) for k, v in list(val.items())[:30]}
    if isinstance(val, list):
        return [_safe_preview(v, max_len=120) for v in val[:20]]
    s = str(val)
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def normalize_filled_code(line: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase N+2 · 输入归一层（无兼容兜底）

    规则：
    1) 只允许 filled_code（strip 后写回）
    2) platform_sku_id 不再作为别名存在：出现即报错（由上游捕获并返回 422）
    3) 若 filled_code 缺失：保持缺失，由 resolver 统一给出 MISSING_FILLED_CODE
    """
    out = dict(line)

    # legacy 字段名在 Phase N+2 中直接禁止
    legacy = out.get("platform_sku_id")
    if legacy is not None and str(legacy).strip():
        raise ValueError("platform_sku_id 已废弃：请使用 filled_code")

    fc = out.get("filled_code")
    if isinstance(fc, str) and fc.strip():
        out["filled_code"] = fc.strip()
        return out

    # 都没有：保持 filled_code 缺失，由 resolver 统一处理
    out.pop("filled_code", None)
    return out


@router.post(
    "/platform-orders/ingest",
    response_model=PlatformOrderIngestOut,
    summary="平台订单接入（Phase N+2）：填写码 → FSKU → Items → /orders",
)
async def ingest_platform_order(
    request: Request,
    payload: PlatformOrderIngestIn = Body(...),
    session: AsyncSession = Depends(get_session),
):
    trace = new_trace("http:/platform-orders/ingest")

    try:
        raw = await request.json()
    except Exception:
        raw = None

    if isinstance(raw, dict) and "address" in raw:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="地址字段应为顶层字段，不支持 address:{...}",
                context={
                    "trace_id": trace.trace_id,
                    "address_preview": _safe_preview(raw.get("address")),
                },
            ),
        )

    plat = norm_platform(payload.platform)

    if payload.store_id is not None:
        store_id = int(payload.store_id)
        try:
            shop_id = norm_shop_id(
                await load_shop_id_by_store_id(session, store_id=store_id, platform=plat)
            )
        except LookupError:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="store_id 不存在",
                    context={"platform": plat, "store_id": store_id},
                ),
            )
    else:
        if payload.shop_id is None:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 或 shop_id 必须提供一个",
                    context={"platform": plat},
                ),
            )
        shop_id = norm_shop_id(payload.shop_id)
        store_id = await resolve_store_id(
            session,
            platform=plat,
            shop_id=shop_id,
            store_name=payload.store_name,
        )

    try:
        address = build_address(payload)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=str(e),
                context={"platform": plat, "store_id": store_id},
            ),
        )

    # ---------- Phase N+2：行级输入仅认 filled_code ----------
    raw_lines = []
    for ln in payload.lines or []:
        ln_dict = ln.model_dump()
        try:
            ln_norm = normalize_filled_code(ln_dict)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message=str(e),
                    context={"platform": plat, "store_id": store_id},
                ),
            )
        raw_lines.append(ln_norm)

    out_dict = await PlatformOrderIngestFlow.run_from_platform_lines(
        session,
        platform=plat,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=payload.ext_order_no,
        occurred_at=payload.occurred_at,
        buyer_name=payload.buyer_name,
        buyer_phone=payload.buyer_phone,
        address=address,
        raw_lines=raw_lines,
        raw_payload=payload.raw_payload,
        trace_id=trace.trace_id,
        extras=None,
    )

    await session.commit()
    return PlatformOrderIngestOut(**out_dict)
