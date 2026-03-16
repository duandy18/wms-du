# app/tms/reports/routes_list.py
#
# 分拆说明：
# - 本文件承载 TMS / Reports（运输报表）明细列表路由；
# - 当前明细口径基于 shipping_records sr 左连 shipping_record_reconciliations r；
# - 不再读取旧 projection 时代已从 shipping_records 剥离的对账快照字段。
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.tms.reports.contracts import ShippingListResponse, ShippingListRow
from app.tms.reports.helpers import (
    build_where_clause,
    clean_opt_str,
    parse_bool_param,
    parse_date_param,
)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-reports/list",
        response_model=ShippingListResponse,
    )
    async def shipping_reports_list(
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        carrier_code: Optional[str] = Query(None),
        province: Optional[str] = Query(None),
        city: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        has_diff: Optional[str] = Query(None),
        min_cost_diff: Optional[float] = Query(None, ge=0),
        min_weight_diff: Optional[float] = Query(None, ge=0),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingListResponse:
        """
        发货明细列表（带过滤条件 + 分页）。

        当前数据口径：
        - shipping_records：物流台帐
        - shipping_record_reconciliations：差异处理表（仅记录有差异的运单）
        """
        try:
            has_diff_parsed = parse_bool_param(has_diff)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        platform_clean = clean_opt_str(platform)
        shop_id_clean = clean_opt_str(shop_id)
        carrier_code_clean = clean_opt_str(carrier_code)
        province_clean = clean_opt_str(province)
        city_clean = clean_opt_str(city)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=platform_clean,
            shop_id=shop_id_clean,
            carrier_code=carrier_code_clean,
            province=province_clean,
            city=city_clean,
            warehouse_id=warehouse_id,
            has_diff=has_diff_parsed,
            min_cost_diff=min_cost_diff,
            min_weight_diff=min_weight_diff,
        )
        params["limit"] = limit
        params["offset"] = offset

        count_sql = text(
            f"""
            SELECT COUNT(*)
            FROM shipping_records sr
            LEFT JOIN shipping_record_reconciliations r
              ON r.shipping_record_id = sr.id
            WHERE {where_sql}
            """
        )
        count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
        total_result = await session.execute(count_sql, count_params)
        total = int(total_result.scalar() or 0)

        sql = text(
            f"""
            SELECT
              sr.id,
              sr.order_ref,
              sr.platform,
              sr.shop_id,
              sr.warehouse_id,
              sr.carrier_code,
              sr.carrier_name,
              sr.tracking_no,
              sr.gross_weight_kg,
              sr.cost_estimated,
              sr.dest_province,
              sr.dest_city,
              sr.created_at,
              r.id IS NOT NULL AS has_diff,
              r.carrier_bill_item_id,
              r.weight_diff_kg,
              r.cost_diff,
              r.adjust_amount
            FROM shipping_records sr
            LEFT JOIN shipping_record_reconciliations r
              ON r.shipping_record_id = sr.id
            WHERE {where_sql}
            ORDER BY sr.created_at DESC, sr.id DESC
            LIMIT :limit OFFSET :offset
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()

        return ShippingListResponse(
            ok=True,
            rows=[
                ShippingListRow(
                    id=int(r["id"]),
                    order_ref=str(r["order_ref"]),
                    platform=str(r["platform"]),
                    shop_id=str(r["shop_id"]),
                    warehouse_id=r.get("warehouse_id"),
                    carrier_code=r.get("carrier_code"),
                    carrier_name=r.get("carrier_name"),
                    tracking_no=r.get("tracking_no"),
                    gross_weight_kg=_to_float(r.get("gross_weight_kg")),
                    cost_estimated=_to_float(r.get("cost_estimated")),
                    dest_province=r.get("dest_province"),
                    dest_city=r.get("dest_city"),
                    has_diff=bool(r.get("has_diff")),
                    carrier_bill_item_id=(
                        int(r["carrier_bill_item_id"])
                        if r.get("carrier_bill_item_id") is not None
                        else None
                    ),
                    weight_diff_kg=_to_float(r.get("weight_diff_kg")),
                    cost_diff=_to_float(r.get("cost_diff")),
                    adjust_amount=_to_float(r.get("adjust_amount")),
                    created_at=r["created_at"].isoformat(),
                )
                for r in rows
            ],
            total=total,
        )
