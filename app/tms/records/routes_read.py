# app/tms/records/routes_read.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读路由；
# - shipping_records 是发货执行流程生成的运输事实台帐；
# - 当前仅提供台帐列表与导出，不提供单条详情 / by-ref / 状态相关入口。
from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.tms.records.contracts import ShippingLedgerListResponse, ShippingLedgerRow
from app.tms.records.repository import export_shipping_ledger_rows, list_shipping_ledger


def _parse_date_param(value: str | None) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    return date.fromisoformat(v)


def _format_csv_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def register(router: APIRouter) -> None:
    @router.get(
        "/tms/records",
        response_model=ShippingLedgerListResponse,
        summary="物流台帐列表",
    )
    async def get_shipping_ledger(
        from_date: str | None = Query(None),
        to_date: str | None = Query(None),
        order_ref: str | None = Query(None),
        tracking_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        province: str | None = Query(None),
        city: str | None = Query(None),
        warehouse_id: int | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShippingLedgerListResponse:
        del current_user

        total, rows = await list_shipping_ledger(
            session=session,
            from_date=_parse_date_param(from_date),
            to_date=_parse_date_param(to_date),
            order_ref=order_ref,
            tracking_no=tracking_no,
            carrier_code=carrier_code,
            province=province,
            city=city,
            warehouse_id=warehouse_id,
            limit=limit,
            offset=offset,
        )

        return ShippingLedgerListResponse(
            ok=True,
            rows=[ShippingLedgerRow(**row) for row in rows],
            total=total,
        )

    @router.get(
        "/tms/records/export",
        summary="导出物流台帐",
    )
    async def export_shipping_ledger(
        from_date: str | None = Query(None),
        to_date: str | None = Query(None),
        order_ref: str | None = Query(None),
        tracking_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        province: str | None = Query(None),
        city: str | None = Query(None),
        warehouse_id: int | None = Query(None),
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> StreamingResponse:
        del current_user

        rows = await export_shipping_ledger_rows(
            session=session,
            from_date=_parse_date_param(from_date),
            to_date=_parse_date_param(to_date),
            order_ref=order_ref,
            tracking_no=tracking_no,
            carrier_code=carrier_code,
            province=province,
            city=city,
            warehouse_id=warehouse_id,
        )

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(
            [
                "发货时间",
                "订单号",
                "运单号",
                "承运商代码",
                "承运商名称",
                "仓库ID",
                "毛重(kg)",
                "预估费用",
                "目的省",
                "目的市",
            ]
        )

        for row in rows:
            created_at = row.get("created_at")
            writer.writerow(
                [
                    _format_csv_value(created_at.isoformat() if hasattr(created_at, "isoformat") else created_at),
                    _format_csv_value(row.get("order_ref")),
                    _format_csv_value(row.get("tracking_no")),
                    _format_csv_value(row.get("carrier_code")),
                    _format_csv_value(row.get("carrier_name")),
                    _format_csv_value(row.get("warehouse_id")),
                    _format_csv_value(row.get("gross_weight_kg")),
                    _format_csv_value(row.get("cost_estimated")),
                    _format_csv_value(row.get("dest_province")),
                    _format_csv_value(row.get("dest_city")),
                ]
            )

        csv_text = "\ufeff" + output.getvalue()
        filename = "shipping-ledger-export.csv"

        return StreamingResponse(
            iter([csv_text]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
