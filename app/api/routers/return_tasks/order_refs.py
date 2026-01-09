# app/api/routers/return_tasks/order_refs.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.return_task import (
    ReturnOrderRefDetailOut,
    ReturnOrderRefItem,
    ReturnOrderRefReceiverOut,
    ReturnOrderRefShippingOut,
    ReturnOrderRefSummaryLine,
    ReturnOrderRefSummaryOut,
)

from ._common import SHIP_OUT_REASONS, calc_remaining_qty, parse_ext_order_no, safe_meta_to_dict


def register_order_refs(router: APIRouter) -> None:
    # ---------------------------------------------------------
    # /order-refs：作业台左侧列表（显示 remaining_qty）
    # ---------------------------------------------------------
    @router.get("/order-refs", response_model=List[ReturnOrderRefItem])
    async def list_return_order_refs(
        session: AsyncSession = Depends(get_session),
        limit: int = Query(20, ge=1, le=200),
        days: int = Query(30, ge=1, le=3650),
        warehouse_id: Optional[int] = Query(None),
    ) -> List[ReturnOrderRefItem]:
        wh_cond = ""
        params: dict = {
            "reasons": list(SHIP_OUT_REASONS),
            "receipt_reason": "RECEIPT",
            "days": int(days),
            "limit": int(limit),
        }
        if warehouse_id is not None:
            wh_cond = "AND warehouse_id = :wid"
            params["wid"] = int(warehouse_id)

        sql = f"""
        WITH shipped AS (
          SELECT ref,
                 warehouse_id,
                 item_id,
                 batch_code,
                 (-delta) AS shipped_qty,
                 occurred_at
            FROM stock_ledger
           WHERE delta < 0
             AND reason = ANY(:reasons)
             AND occurred_at >= now() - (:days || ' days')::interval
             {wh_cond}
        ),
        shipped_refs AS (
          SELECT DISTINCT ref FROM shipped
        ),
        returned AS (
          SELECT l.ref,
                 l.warehouse_id,
                 l.item_id,
                 l.batch_code,
                 (l.delta) AS returned_qty,
                 l.occurred_at
            FROM stock_ledger l
            JOIN shipped_refs r ON r.ref = l.ref
           WHERE l.delta > 0
             AND l.reason = :receipt_reason
             AND l.occurred_at >= now() - (:days || ' days')::interval
             {wh_cond}
        ),
        ship_sum AS (
          SELECT ref,
                 COUNT(*)::int AS total_lines,
                 CASE WHEN COUNT(DISTINCT warehouse_id)=1 THEN MIN(warehouse_id) ELSE NULL END AS warehouse_id,
                 MAX(occurred_at) AS last_ship_at,
                 COALESCE(SUM(shipped_qty), 0)::int AS shipped_total
            FROM shipped
           GROUP BY ref
        ),
        ret_sum AS (
          SELECT ref,
                 COALESCE(SUM(returned_qty), 0)::int AS returned_total
            FROM returned
           GROUP BY ref
        )
        SELECT s.ref AS order_ref,
               s.warehouse_id AS warehouse_id,
               s.last_ship_at AS last_ship_at,
               s.total_lines AS total_lines,
               GREATEST((s.shipped_total - COALESCE(r.returned_total, 0)), 0)::int AS remaining_qty
          FROM ship_sum s
          LEFT JOIN ret_sum r ON r.ref = s.ref
         WHERE (s.shipped_total - COALESCE(r.returned_total, 0)) > 0
         ORDER BY s.last_ship_at DESC
         LIMIT :limit
        """

        rows = (await session.execute(sa.text(sql), params)).mappings().all()
        return [ReturnOrderRefItem(**dict(r)) for r in rows]

    # ---------------------------------------------------------
    # /order-refs/{order_ref}/summary：出库摘要（只读事实）
    # ---------------------------------------------------------
    @router.get("/order-refs/{order_ref}/summary", response_model=ReturnOrderRefSummaryOut)
    async def get_return_order_ref_summary(
        order_ref: str,
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
    ) -> ReturnOrderRefSummaryOut:
        wh_cond = ""
        params: dict = {"ref": order_ref, "reasons": list(SHIP_OUT_REASONS)}
        if warehouse_id is not None:
            wh_cond = "AND l.warehouse_id = :wid"
            params["wid"] = int(warehouse_id)

        # ✅ 作业人员视角：把 item_name 一并 join 出来，前端不再只能展示 item_id
        sql = f"""
        SELECT l.warehouse_id,
               l.item_id,
               i.name AS item_name,
               l.batch_code,
               COALESCE(SUM(-l.delta), 0)::int AS shipped_qty
          FROM stock_ledger l
          LEFT JOIN items i ON i.id = l.item_id
         WHERE l.ref = :ref
           AND l.delta < 0
           AND l.reason = ANY(:reasons)
           {wh_cond}
         GROUP BY l.warehouse_id, l.item_id, i.name, l.batch_code
         ORDER BY l.warehouse_id, l.item_id, l.batch_code
        """

        lines_raw = (await session.execute(sa.text(sql), params)).mappings().all()
        lines = [ReturnOrderRefSummaryLine(**dict(r)) for r in lines_raw]

        rs = await session.execute(
            sa.text(
                """
                SELECT DISTINCT reason
                  FROM stock_ledger
                 WHERE ref=:ref
                   AND delta<0
                   AND reason = ANY(:reasons)
                 ORDER BY reason
                """
            ),
            {"ref": order_ref, "reasons": list(SHIP_OUT_REASONS)},
        )
        reasons = [str(x[0]) for x in rs.all()]
        return ReturnOrderRefSummaryOut(order_ref=order_ref, ship_reasons=reasons, lines=lines)

    # ---------------------------------------------------------
    # /order-refs/{order_ref}/detail：订单详情（只读）
    # shipping_records + summary + remaining_qty
    # ---------------------------------------------------------
    @router.get("/order-refs/{order_ref}/detail", response_model=ReturnOrderRefDetailOut)
    async def get_return_order_ref_detail(
        order_ref: str,
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
    ) -> ReturnOrderRefDetailOut:
        summary = await get_return_order_ref_summary(order_ref, session=session, warehouse_id=warehouse_id)
        remaining_qty = await calc_remaining_qty(session, order_ref=order_ref, warehouse_id=warehouse_id)

        ship_row = (
            await session.execute(
                sa.text(
                    """
                    SELECT platform,
                           shop_id,
                           carrier_code,
                           carrier_name,
                           tracking_no,
                           status,
                           created_at,
                           gross_weight_kg,
                           cost_estimated,
                           meta
                      FROM shipping_records
                     WHERE order_ref = :ref
                     ORDER BY created_at DESC
                     LIMIT 1
                    """
                ),
                {"ref": order_ref},
            )
        ).mappings().first()

        platform = None
        shop_id = None
        ext_order_no = parse_ext_order_no(order_ref)

        shipping = None
        if ship_row:
            platform = str(ship_row.get("platform") or "") or None
            shop_id = str(ship_row.get("shop_id") or "") or None

            meta_dict = safe_meta_to_dict(ship_row.get("meta"))
            recv_dict = meta_dict.get("receiver") if isinstance(meta_dict, dict) else None
            receiver = None
            if isinstance(recv_dict, dict):
                receiver = ReturnOrderRefReceiverOut(
                    name=recv_dict.get("name"),
                    phone=recv_dict.get("phone"),
                    province=recv_dict.get("province"),
                    city=recv_dict.get("city"),
                    district=recv_dict.get("district"),
                    detail=recv_dict.get("detail"),
                )

            gross = ship_row.get("gross_weight_kg")
            cost = ship_row.get("cost_estimated")

            shipping = ReturnOrderRefShippingOut(
                tracking_no=ship_row.get("tracking_no"),
                carrier_code=ship_row.get("carrier_code"),
                carrier_name=ship_row.get("carrier_name"),
                status=ship_row.get("status"),
                shipped_at=ship_row.get("created_at"),
                gross_weight_kg=float(gross) if gross is not None else None,
                cost_estimated=float(cost) if cost is not None else None,
                receiver=receiver,
                meta=meta_dict or None,
            )

        return ReturnOrderRefDetailOut(
            order_ref=order_ref,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            remaining_qty=remaining_qty,
            shipping=shipping,
            summary=summary,
        )
