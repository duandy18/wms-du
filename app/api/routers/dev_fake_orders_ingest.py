# app/api/routers/dev_fake_orders_ingest.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
    load_shop_id_by_store_id as load_shop_id_by_store_id_for_ingest,
)
from app.api.routers.platform_orders_ingest_routes import normalize_filled_code


async def run_single_ingest(
    session: AsyncSession,
    order: Dict[str, Any],
    *,
    dev_batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    trace = new_trace("dev:/dev/fake-orders/ingest")

    plat = norm_platform(str(order.get("platform") or ""))
    if not plat:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="platform 不能为空",
                context={"trace_id": trace.trace_id},
            ),
        )

    ext_order_no = str(order.get("ext_order_no") or "").strip()
    if not ext_order_no:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="ext_order_no 不能为空",
                context={"platform": plat},
            ),
        )

    # store_id / shop_id 解析（devtools 订单一般提供 shop_id）
    if order.get("store_id") is not None:
        store_id = int(order["store_id"])
        shop_id = norm_shop_id(
            await load_shop_id_by_store_id_for_ingest(
                session,
                store_id=store_id,
                platform=plat,
            )
        )
    else:
        raw_shop_id = order.get("shop_id")
        if raw_shop_id is None:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 或 shop_id 必须提供一个",
                    context={"platform": plat},
                ),
            )
        shop_id = norm_shop_id(str(raw_shop_id))
        store_id = await resolve_store_id(
            session,
            platform=plat,
            shop_id=shop_id,
            store_name=order.get("store_name"),
        )

    # address：生成器默认带地址，但这里仍保留容错（不应 500）
    address = None
    try:

        class _P:
            def __init__(self, d: Dict[str, Any]):
                self.__dict__.update(d)

            def __getattr__(self, name: str):
                return None

        address = build_address(_P(order))
    except Exception:
        address = None

    raw_lines: List[Dict[str, Any]] = []
    for ln in order.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        try:
            ln_norm = normalize_filled_code(ln)
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

    # raw_payload：带上 devtools 标签，便于追踪/清理
    raw_payload = order.get("raw_payload")
    if raw_payload is None:
        raw_payload = {}
    if isinstance(raw_payload, dict):
        raw_payload = {
            **raw_payload,
            "_devtools": True,
            "dev_batch_id": dev_batch_id,
            "source": "dev/fake-orders/ingest",
        }

    extras: Dict[str, Any] = {"source": "dev/fake-orders/ingest"}
    if dev_batch_id is not None:
        extras["dev_batch_id"] = dev_batch_id
        extras["devtools"] = True

    out_dict = await PlatformOrderIngestFlow.run_from_platform_lines(
        session,
        platform=plat,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=ext_order_no,
        occurred_at=order.get("occurred_at"),
        buyer_name=order.get("buyer_name"),
        buyer_phone=order.get("buyer_phone"),
        address=address,
        raw_lines=raw_lines,
        raw_payload=raw_payload,
        trace_id=trace.trace_id,
        source="dev/fake-orders/ingest",
        extras=extras,
    )

    await session.commit()
    return out_dict
