# app/api/routers/shipping_reports_routes_list.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_reports_helpers import (
    build_where_clause,
    clean_opt_str,
    parse_date_param,
)
from app.api.routers.shipping_reports_schemas import ShippingListResponse, ShippingListRow


def register(router: APIRouter) -> None:
    # ----------------- list（明细列表） -----------------
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
        district: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        reconcile_status: Optional[str] = Query(None),
        min_cost_diff: Optional[float] = Query(None, ge=0),
        min_weight_diff: Optional[float] = Query(None, ge=0),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingListResponse:
        """
        发货明细列表（带过滤条件 + 分页）。
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        platform_clean = clean_opt_str(platform)
        shop_id_clean = clean_opt_str(shop_id)
        carrier_code_clean = clean_opt_str(carrier_code)
        province_clean = clean_opt_str(province)
        city_clean = clean_opt_str(city)
        district_clean = clean_opt_str(district)
        reconcile_status_clean = clean_opt_str(reconcile_status)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=platform_clean,
            shop_id=shop_id_clean,
            carrier_code=carrier_code_clean,
            province=province_clean,
            warehouse_id=warehouse_id,
            city=city_clean,
            district=district_clean,
            reconcile_status=reconcile_status_clean,
            min_cost_diff=min_cost_diff,
            min_weight_diff=min_weight_diff,
            include_province_filter=True,
        )
        params["limit"] = limit
        params["offset"] = offset

        # 总数
        count_sql = text(f"SELECT COUNT(*) FROM shipping_records WHERE {where_sql}")
        count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
        total_result = await session.execute(count_sql, count_params)
        total = int(total_result.scalar() or 0)

        sql = text(
            f"""
            SELECT
              id,
              order_ref,
              platform,
              shop_id,
              warehouse_id,
              trace_id,
              carrier_code,
              carrier_name,
              tracking_no,
              gross_weight_kg,
              packaging_weight_kg,
              cost_estimated,
              cost_real,
              billing_weight_kg,
              freight_amount,
              surcharge_amount,
              weight_diff_kg,
              cost_diff,
              reconcile_status,
              reconciled_at,
              status,
              meta,
              created_at
            FROM shipping_records
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
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
                    trace_id=r.get("trace_id"),
                    carrier_code=r.get("carrier_code"),
                    carrier_name=r.get("carrier_name"),
                    tracking_no=r.get("tracking_no"),
                    gross_weight_kg=(
                        float(r["gross_weight_kg"]) if r["gross_weight_kg"] is not None else None
                    ),
                    packaging_weight_kg=(
                        float(r["packaging_weight_kg"])
                        if r["packaging_weight_kg"] is not None
                        else None
                    ),
                    cost_estimated=(
                        float(r["cost_estimated"]) if r["cost_estimated"] is not None else None
                    ),
                    cost_real=(
                        float(r["cost_real"]) if r["cost_real"] is not None else None
                    ),
                    billing_weight_kg=(
                        float(r["billing_weight_kg"])
                        if r["billing_weight_kg"] is not None
                        else None
                    ),
                    freight_amount=(
                        float(r["freight_amount"]) if r["freight_amount"] is not None else None
                    ),
                    surcharge_amount=(
                        float(r["surcharge_amount"])
                        if r["surcharge_amount"] is not None
                        else None
                    ),
                    weight_diff_kg=(
                        float(r["weight_diff_kg"]) if r["weight_diff_kg"] is not None else None
                    ),
                    cost_diff=(
                        float(r["cost_diff"]) if r["cost_diff"] is not None else None
                    ),
                    reconcile_status=r.get("reconcile_status"),
                    reconciled_at=(
                        r["reconciled_at"].isoformat() if r.get("reconciled_at") is not None else None
                    ),
                    status=r.get("status"),
                    meta=r.get("meta"),
                    created_at=r["created_at"].isoformat(),
                )
                for r in rows
            ],
            total=total,
        )
