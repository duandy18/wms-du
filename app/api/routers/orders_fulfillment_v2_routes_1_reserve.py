# app/api/routers/orders_fulfillment_v2_routes_1_reserve.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import ReserveRequest, ReserveResponse
from app.services.audit_writer import AuditEventWriter
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService


class FulfillmentOverrideRequest(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=500)


class FulfillmentOverrideResponse(BaseModel):
    status: str
    ref: str
    from_warehouse_id: Optional[int] = None
    to_warehouse_id: int
    fulfillment_status: str


async def _get_order_id_and_current_wh(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> tuple[int, Optional[int]]:
    row = await session.execute(
        text(
            """
            SELECT id, warehouse_id
              FROM orders
             WHERE platform = :p
               AND shop_id  = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id, "o": ext_order_no},
    )
    rec = row.first()
    if rec is None:
        raise ValueError(f"order not found: platform={platform}, shop_id={shop_id}, ext_order_no={ext_order_no}")
    oid = int(rec[0])
    wid = rec[1]
    return oid, (int(wid) if wid else None)


async def _load_order_lines_sum(
    session: AsyncSession,
    *,
    order_id: int,
) -> List[Dict[str, Any]]:
    """
    返回整单需求：[{item_id, qty}]
    """
    rows = await session.execute(
        text(
            """
            SELECT item_id, SUM(COALESCE(qty, 0)) AS qty
              FROM order_items
             WHERE order_id = :oid
             GROUP BY item_id
             ORDER BY item_id
            """
        ),
        {"oid": int(order_id)},
    )
    lines: List[Dict[str, Any]] = []
    for item_id, qty in rows.fetchall():
        q = int(qty or 0)
        if q <= 0:
            continue
        lines.append({"item_id": int(item_id), "qty": q})
    return lines


async def _check_can_fulfill_whole_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    lines: List[Dict[str, Any]],
) -> None:
    """
    路线 C：只做约束校验，不自动找其他仓。
    校验失败直接抛 ValueError（由路由转 409）。
    """
    if not lines:
        raise ValueError("cannot override fulfillment: order has no lines")

    svc = ChannelInventoryService()
    insufficient: List[Dict[str, Any]] = []

    for line in lines:
        item_id = int(line["item_id"])
        need = int(line["qty"])
        available_raw = await svc.get_available_for_item(
            session=session,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=int(warehouse_id),
            item_id=item_id,
        )
        if need > int(available_raw):
            insufficient.append(
                {
                    "item_id": item_id,
                    "need": need,
                    "available": int(available_raw),
                }
            )

    if insufficient:
        raise ValueError(
            "override blocked: target warehouse cannot fulfill whole order; "
            f"platform={platform}, shop={shop_id}, wh={warehouse_id}, insufficient={insufficient}"
        )


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/reserve",
        response_model=ReserveResponse,
    )
    async def order_reserve(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ReserveRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        if not body.lines:
            return ReserveResponse(
                status="OK",
                ref=f"ORD:{plat}:{shop_id}:{ext_order_no}",
                reservation_id=None,
                lines=0,
            )

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        # Route C 合同护栏：
        # reserve 不负责“选仓/兜底”，只允许在订单已具备明确履约仓且处于可履约态时继续。
        row = await session.execute(
            text(
                """
                SELECT warehouse_id, fulfillment_status, blocked_reasons, blocked_detail
                  FROM orders
                 WHERE platform = :p
                   AND shop_id  = :s
                   AND ext_order_no = :o
                 LIMIT 1
                """
            ),
            {"p": plat, "s": shop_id, "o": ext_order_no},
        )
        rec = row.first()
        if rec is None:
            raise HTTPException(409, detail=f"reserve blocked: order not found: {order_ref}")

        warehouse_id, fulfillment_status, blocked_reasons, blocked_detail = rec
        whid = int(warehouse_id) if warehouse_id is not None else None
        fstat = str(fulfillment_status or "")

        if whid is None or fstat != "READY_TO_FULFILL":
            if fstat == "FULFILLMENT_BLOCKED":
                raise HTTPException(
                    409,
                    detail=f"reserve blocked: order is FULFILLMENT_BLOCKED; reasons={blocked_reasons}; detail={blocked_detail}",
                )
            raise HTTPException(
                409,
                detail=f"reserve blocked: order not READY_TO_FULFILL or warehouse_id missing; status={fstat}, warehouse_id={whid}",
            )

        try:
            result = await OrderService.reserve(
                session,
                platform=plat,
                shop_id=shop_id,
                ref=order_ref,
                lines=[{"item_id": line.item_id, "qty": line.qty} for line in body.lines],
                trace_id=trace_id,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return ReserveResponse(
            status=result.get("status", "OK"),
            ref=result.get("ref", order_ref),
            reservation_id=result.get("reservation_id"),
            lines=result.get("lines", len(body.lines)),
        )

    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/fulfillment/override",
        response_model=FulfillmentOverrideResponse,
    )
    async def fulfillment_override(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: FulfillmentOverrideRequest,
        session: AsyncSession = Depends(get_session),
        user: Any = Depends(get_current_user),
    ):
        plat = platform.upper()

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        try:
            order_id, from_wh = await _get_order_id_and_current_wh(
                session,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
            )

            lines = await _load_order_lines_sum(session, order_id=order_id)

            # 关键：只校验 body.warehouse_id 这一个目标仓
            await _check_can_fulfill_whole_order(
                session,
                platform=plat,
                shop_id=shop_id,
                warehouse_id=int(body.warehouse_id),
                lines=lines,
            )

            overridden_by = getattr(user, "id", None)

            # 显性兜底：写入订单履约字段 + 清空 blocked
            await session.execute(
                text(
                    """
                    UPDATE orders
                       SET warehouse_id = :wid,
                           fulfillment_warehouse_id = :wid,
                           fulfillment_status = 'FULFILLMENT_OVERRIDDEN',
                           overridden_by = :by,
                           overridden_at = now(),
                           override_reason = :reason,
                           blocked_reasons = NULL,
                           blocked_detail = NULL
                     WHERE id = :oid
                    """
                ),
                {
                    "wid": int(body.warehouse_id),
                    "by": int(overridden_by) if overridden_by is not None else None,
                    "reason": body.reason.strip(),
                    "oid": int(order_id),
                },
            )

            # 审计事件（尽量写，失败不影响业务）
            try:
                await AuditEventWriter.write(
                    session,
                    flow="OUTBOUND",
                    event="FULFILLMENT_OVERRIDDEN",
                    ref=order_ref,
                    trace_id=trace_id,
                    meta={
                        "platform": plat,
                        "shop": shop_id,
                        "from_warehouse_id": from_wh,
                        "to_warehouse_id": int(body.warehouse_id),
                        "reason": body.reason.strip(),
                        "overridden_by": overridden_by,
                    },
                    auto_commit=False,
                )
            except Exception:
                pass

            await session.commit()

        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return FulfillmentOverrideResponse(
            status="OK",
            ref=order_ref,
            from_warehouse_id=from_wh,
            to_warehouse_id=int(body.warehouse_id),
            fulfillment_status="FULFILLMENT_OVERRIDDEN",
        )
