# app/tms/billing/routes_reconciliations.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts import (
    CarrierBillItemOut,
    ShippingBillReconciliationDetailResponse,
    ShippingBillReconciliationOut,
    ShippingBillReconciliationsResponse,
    ShippingBillReconciliationRowOut,
    ShippingBillReconciliationShippingRecordOut,
)

from .repository_reconciliations import (
    get_shipping_bill_reconciliation_detail,
    list_shipping_bill_reconciliations,
)

ReconciliationStatus = Literal["diff", "bill_only", "record_only"]


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float(v)  # type: ignore[arg-type]


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-bills/reconciliations",
        response_model=ShippingBillReconciliationsResponse,
    )
    async def get_shipping_bill_reconciliations(
        carrier_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        status: ReconciliationStatus | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingBillReconciliationsResponse:
        total, rows = await list_shipping_bill_reconciliations(
            session,
            carrier_code=(
                carrier_code.strip()
                if isinstance(carrier_code, str) and carrier_code.strip()
                else None
            ),
            tracking_no=(
                tracking_no.strip()
                if isinstance(tracking_no, str) and tracking_no.strip()
                else None
            ),
            status=status,
            limit=limit,
            offset=offset,
        )

        return ShippingBillReconciliationsResponse(
            ok=True,
            rows=[
                ShippingBillReconciliationRowOut(
                    reconciliation_id=int(r["reconciliation_id"]),
                    status=str(r["status"]),
                    carrier_code=str(r["carrier_code"]),
                    tracking_no=str(r["tracking_no"]),
                    shipping_record_id=(
                        int(r["shipping_record_id"])
                        if r.get("shipping_record_id") is not None
                        else None
                    ),
                    carrier_bill_item_id=(
                        int(r["carrier_bill_item_id"])
                        if r.get("carrier_bill_item_id") is not None
                        else None
                    ),
                    business_time=r.get("business_time"),
                    destination_province=r.get("destination_province"),
                    destination_city=r.get("destination_city"),
                    billing_weight_kg=_to_float(r.get("billing_weight_kg")),
                    gross_weight_kg=_to_float(r.get("gross_weight_kg")),
                    weight_diff_kg=_to_float(r.get("weight_diff_kg")),
                    freight_amount=_to_float(r.get("freight_amount")),
                    surcharge_amount=_to_float(r.get("surcharge_amount")),
                    bill_cost_real=_to_float(r.get("bill_cost_real")),
                    total_amount=_to_float(r.get("total_amount")),
                    cost_estimated=_to_float(r.get("cost_estimated")),
                    cost_diff=_to_float(r.get("cost_diff")),
                    adjust_amount=_to_float(r.get("adjust_amount")),
                    created_at=r["created_at"],
                )
                for r in rows
            ],
            total=total,
        )

    @router.get(
        "/shipping-bills/reconciliations/{reconciliation_id}",
        response_model=ShippingBillReconciliationDetailResponse,
    )
    async def get_shipping_bill_reconciliation(
        reconciliation_id: int,
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingBillReconciliationDetailResponse:
        row = await get_shipping_bill_reconciliation_detail(
            session,
            reconciliation_id=reconciliation_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="对账异常记录不存在。")

        bill_item = None
        if row.get("bill_id") is not None:
            bill_item = CarrierBillItemOut(
                id=int(row["bill_id"]),
                carrier_code=str(row["bill_carrier_code"]),
                bill_month=row.get("bill_month"),
                tracking_no=str(row["bill_tracking_no"]),
                business_time=row.get("business_time"),
                destination_province=row.get("destination_province"),
                destination_city=row.get("destination_city"),
                billing_weight_kg=_to_float(row.get("billing_weight_kg")),
                freight_amount=_to_float(row.get("freight_amount")),
                surcharge_amount=_to_float(row.get("surcharge_amount")),
                total_amount=_to_float(row.get("total_amount")),
                settlement_object=row.get("settlement_object"),
                order_customer=row.get("order_customer"),
                sender_name=row.get("sender_name"),
                network_name=row.get("network_name"),
                size_text=row.get("size_text"),
                parent_customer=row.get("parent_customer"),
                raw_payload=dict(row.get("raw_payload") or {}),
                created_at=row["bill_created_at"],
            )

        shipping_record = None
        if row.get("record_id") is not None:
            shipping_record = ShippingBillReconciliationShippingRecordOut(
                id=int(row["record_id"]),
                order_ref=str(row["order_ref"]),
                platform=str(row["platform"]),
                shop_id=str(row["shop_id"]),
                carrier_code=row.get("record_carrier_code"),
                carrier_name=row.get("carrier_name"),
                tracking_no=(
                    str(row["record_tracking_no"])
                    if row.get("record_tracking_no") is not None
                    else None
                ),
                gross_weight_kg=_to_float(row.get("gross_weight_kg")),
                cost_estimated=_to_float(row.get("cost_estimated")),
                warehouse_id=int(row["warehouse_id"]),
                shipping_provider_id=int(row["shipping_provider_id"]),
                dest_province=row.get("dest_province"),
                dest_city=row.get("dest_city"),
                created_at=row["record_created_at"],
            )

        return ShippingBillReconciliationDetailResponse(
            ok=True,
            reconciliation=ShippingBillReconciliationOut(
                id=int(row["reconciliation_id"]),
                status=str(row["status"]),
                carrier_code=str(row["carrier_code"]),
                tracking_no=str(row["tracking_no"]),
                shipping_record_id=(
                    int(row["shipping_record_id"])
                    if row.get("shipping_record_id") is not None
                    else None
                ),
                carrier_bill_item_id=(
                    int(row["carrier_bill_item_id"])
                    if row.get("carrier_bill_item_id") is not None
                    else None
                ),
                weight_diff_kg=_to_float(row.get("weight_diff_kg")),
                cost_diff=_to_float(row.get("cost_diff")),
                adjust_amount=_to_float(row.get("adjust_amount")),
                created_at=row["reconciliation_created_at"],
            ),
            bill_item=bill_item,
            shipping_record=shipping_record,
        )
