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


def _format_dims(row: dict[str, object]) -> str:
    length_cm = row.get("length_cm")
    width_cm = row.get("width_cm")
    height_cm = row.get("height_cm")
    if length_cm is None or width_cm is None or height_cm is None:
        return ""
    return f"{length_cm}×{width_cm}×{height_cm}"


def register(router: APIRouter) -> None:
    @router.get(
        "",
        response_model=ShippingLedgerListResponse,
        summary="物流台帐列表",
    )
    async def get_shipping_ledger(
        from_date: str | None = Query(None),
        to_date: str | None = Query(None),
        order_ref: str | None = Query(None),
        tracking_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        shipping_provider_id: int | None = Query(None, ge=1),
        province: str | None = Query(None),
        city: str | None = Query(None),
        warehouse_id: int | None = Query(None, ge=1),
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
            shipping_provider_id=shipping_provider_id,
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
        "/export",
        summary="导出物流台帐",
    )
    async def export_shipping_ledger(
        from_date: str | None = Query(None),
        to_date: str | None = Query(None),
        order_ref: str | None = Query(None),
        tracking_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        shipping_provider_id: int | None = Query(None, ge=1),
        province: str | None = Query(None),
        city: str | None = Query(None),
        warehouse_id: int | None = Query(None, ge=1),
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
            shipping_provider_id=shipping_provider_id,
            province=province,
            city=city,
            warehouse_id=warehouse_id,
        )

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(
            [
                "运单号",
                "快递网点",
                "订单号",
                "预估运费",
                "附加费",
                "预估总费用",
                "毛重(kg)",
                "长×宽×高(cm)",
                "仓库",
                "目的省",
                "目的市",
                "寄件人",
                "发货时间",
            ]
        )

        for row in rows:
            created_at = row.get("created_at")
            provider_text = ""
            carrier_name = row.get("carrier_name")
            carrier_code = row.get("carrier_code")
            if carrier_name and carrier_code:
                provider_text = f"{carrier_name}（{carrier_code}）"
            elif carrier_name:
                provider_text = str(carrier_name)
            elif carrier_code:
                provider_text = str(carrier_code)

            writer.writerow(
                [
                    _format_csv_value(row.get("tracking_no")),
                    _format_csv_value(provider_text),
                    _format_csv_value(row.get("order_ref")),
                    _format_csv_value(row.get("freight_estimated")),
                    _format_csv_value(row.get("surcharge_estimated")),
                    _format_csv_value(row.get("cost_estimated")),
                    _format_csv_value(row.get("gross_weight_kg")),
                    _format_csv_value(_format_dims(row)),
                    _format_csv_value(row.get("warehouse_id")),
                    _format_csv_value(row.get("dest_province")),
                    _format_csv_value(row.get("dest_city")),
                    _format_csv_value(row.get("sender")),
                    _format_csv_value(created_at.isoformat() if hasattr(created_at, "isoformat") else created_at),
                ]
            )

        csv_text = "\ufeff" + output.getvalue()
        filename = "shipping-ledger-export.csv"

        return StreamingResponse(
            iter([csv_text]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
