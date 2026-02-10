# app/api/routers/platform_orders_confirm_create.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.platform_order_manual_decisions_service import (
    ManualDecisionRow,
    insert_manual_decisions_batch,
    new_batch_id,
)
from app.services.platform_order_resolve_service import (
    load_items_brief,
    norm_platform,
    resolve_platform_lines_to_items,
)

from app.api.routers.platform_orders_confirm_create_schemas import (
    PlatformOrderConfirmCreateIn,
    PlatformOrderConfirmCreateOut,
)
from app.api.routers.platform_orders_fact_repo import (
    line_key_from_inputs,
    load_fact_lines_for_order,
    load_shop_id_by_store_id,
)
from app.api.routers.platform_orders_ingest_helpers import load_order_fulfillment_brief
from app.api.routers.platform_orders_shared import (
    build_items_payload_from_item_qty_map,
    collect_risk_flags_from_unresolved,
    validate_and_build_item_qty_map,
)

router = APIRouter(tags=["platform-orders"])


def _get(d: Any, k: str) -> Any:
    if isinstance(d, dict):
        return d.get(k)
    return getattr(d, k, None)


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


def _as_str(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


async def _load_latest_manual_batch_id_for_order(
    session: AsyncSession, *, order_id: int
) -> Optional[str]:
    row = (
        await session.execute(
            text(
                """
                SELECT batch_id
                  FROM platform_order_manual_decisions
                 WHERE order_id = :order_id
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                """
            ),
            {"order_id": int(order_id)},
        )
    ).mappings().first()
    if not row:
        return None
    bid = row.get("batch_id")
    return str(bid) if bid is not None else None


@router.post(
    "/platform-orders/confirm-and-create",
    response_model=PlatformOrderConfirmCreateOut,
    summary="当单执行：人工确认选货后生成内部订单（不写任何映射；人工决策写入证据表）",
)
async def confirm_and_create_platform_order(
    payload: PlatformOrderConfirmCreateIn = Body(...),
    session: AsyncSession = Depends(get_session),
):
    trace = new_trace("http:/platform-orders/confirm-and-create")

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
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "trace_id": trace.trace_id,
                },
            ),
        )

    # Phase N+4：对外彻底分层——禁用内部幂等锚点 line_key 作为输入
    # 同时继续拒绝 platform_sku_id（legacy）
    for d in (payload.decisions or []):
        if _as_str(_get(d, "platform_sku_id")):
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="platform_sku_id 已废弃：请使用 filled_code",
                    context={
                        "platform": plat,
                        "store_id": store_id,
                        "ext_order_no": ext,
                        "trace_id": trace.trace_id,
                    },
                ),
            )
        if _as_str(_get(d, "line_key")):
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="line_key 为内部幂等锚点，禁止外部输入：请使用 locator_kind/locator_value 或 filled_code 或 line_no",
                    context={
                        "platform": plat,
                        "store_id": store_id,
                        "ext_order_no": ext,
                        "trace_id": trace.trace_id,
                    },
                ),
            )

    try:
        shop_id = await load_shop_id_by_store_id(session, store_id=store_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="store_id 不存在",
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "ext_order_no": ext,
                    "trace_id": trace.trace_id,
                },
            ),
        )

    fact_lines = await load_fact_lines_for_order(
        session, platform=plat, store_id=store_id, ext_order_no=ext
    )
    if not fact_lines:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="未找到该订单的事实行（请先 ingest 落事实）",
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "ext_order_no": ext,
                    "trace_id": trace.trace_id,
                },
            ),
        )

    # Phase N+2：不再补齐 filled_code；facts 里缺失就让 resolver/校验直接报错

    try:
        item_qty_map, audit_decisions = validate_and_build_item_qty_map(
            fact_lines=fact_lines,
            decisions=payload.decisions,
            line_key_from_inputs=line_key_from_inputs,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=str(e),
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "ext_order_no": ext,
                    "trace_id": trace.trace_id,
                },
            ),
        )

    _, unresolved, _ = await resolve_platform_lines_to_items(
        session, platform=plat, store_id=store_id, lines=fact_lines
    )
    risk_flags = collect_risk_flags_from_unresolved(unresolved)

    item_ids = sorted(item_qty_map.keys())
    items_brief = await load_items_brief(session, item_ids=item_ids)

    items_payload = build_items_payload_from_item_qty_map(
        item_qty_map=item_qty_map,
        items_brief=items_brief,
        store_id=store_id,
        source="platform-orders/confirm-and-create",
        extras=None,
    )

    extras: Dict[str, Any] = {
        "store_id": store_id,
        "source": "platform-orders/confirm-and-create",
        "trace_id": trace.trace_id,
    }

    r: Dict[str, Any] = {}
    oid: Optional[int] = None
    ref: Optional[str] = None
    manual_batch_id: Optional[str] = None

    try:
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
            extras=extras,
            trace_id=trace.trace_id,
        )

        oid = int(r.get("id") or 0) if r.get("id") is not None else None
        ref = str(r.get("ref") or f"ORD:{plat}:{shop_id}:{ext}")
        status = str(r.get("status") or "OK").strip().upper()

        if status == "IDEMPOTENT" and oid is not None:
            manual_batch_id = await _load_latest_manual_batch_id_for_order(
                session, order_id=int(oid)
            )
        else:
            batch_id = new_batch_id()
            manual_batch_id = str(batch_id)

            # Phase N+4：证据表写入的 line_key/line_no/filled_code/fact_qty 必须来自事实行审计（audit_decisions）
            # 这样 line_key 永远不会被外部输入污染。
            rows = []
            decisions_in = list(payload.decisions or [])
            if len(decisions_in) != len(audit_decisions):
                raise HTTPException(
                    status_code=500,
                    detail=make_problem(
                        status_code=500,
                        error_code="internal_error",
                        message="audit_decisions 数量与 decisions 不一致",
                        context={
                            "platform": plat,
                            "store_id": store_id,
                            "ext_order_no": ext,
                            "trace_id": trace.trace_id,
                            "decisions_n": len(decisions_in),
                            "audit_decisions_n": len(audit_decisions),
                        },
                    ),
                )

            for d, ad in zip(decisions_in, audit_decisions):
                item_id = _as_int(_get(d, "item_id")) or 0
                qty = _as_int(_get(d, "qty")) or 0
                note = _as_str(_get(d, "note"))

                line_key = _as_str(ad.get("line_key"))
                line_no = _as_int(ad.get("line_no"))
                filled_code_raw = _as_str(ad.get("filled_code"))
                fact_qty = _as_int(ad.get("fact_qty"))

                rows.append(
                    ManualDecisionRow(
                        platform=plat,
                        store_id=store_id,
                        ext_order_no=ext,
                        order_id=oid,
                        line_key=line_key,
                        line_no=line_no,
                        filled_code=filled_code_raw,
                        fact_qty=fact_qty,
                        item_id=item_id,
                        qty=qty,
                        note=note,
                        manual_reason=_as_str(getattr(payload, "reason", None)),
                        risk_flags=[str(x) for x in risk_flags if isinstance(x, str)],
                    )
                )

            if rows:
                await insert_manual_decisions_batch(
                    session=session, batch_id=batch_id, rows=rows
                )

        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise

    fulfillment_status = None
    blocked_reasons = None
    if oid is not None:
        fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(
            session, order_id=oid
        )

    return PlatformOrderConfirmCreateOut(
        status=str(r.get("status") or "OK"),
        id=oid,
        ref=str(ref or f"ORD:{plat}:{shop_id}:{ext}"),
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
        manual_override=True,
        manual_reason=getattr(payload, "reason", None),
        manual_batch_id=manual_batch_id,
        risk_flags=[str(x) for x in risk_flags if isinstance(x, str)],
        facts_n=len(fact_lines),
        fulfillment_status=fulfillment_status,
        blocked_reasons=blocked_reasons,
    )
