# app/tms/billing/routes_items.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts import CarrierBillItemOut, CarrierBillItemsResponse
from .repository import list_carrier_bill_items


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
        "/shipping-bills/items",
        response_model=CarrierBillItemsResponse,
    )
    async def get_shipping_bill_items(
        import_batch_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> CarrierBillItemsResponse:
        total, rows = await list_carrier_bill_items(
            session,
            import_batch_no=import_batch_no.strip() if isinstance(import_batch_no, str) and import_batch_no.strip() else None,
            carrier_code=carrier_code.strip() if isinstance(carrier_code, str) and carrier_code.strip() else None,
            tracking_no=tracking_no.strip() if isinstance(tracking_no, str) and tracking_no.strip() else None,
            limit=limit,
            offset=offset,
        )

        return CarrierBillItemsResponse(
            ok=True,
            rows=[
                CarrierBillItemOut(
                    id=int(r["id"]),
                    import_batch_no=str(r["import_batch_no"]),
                    carrier_code=str(r["carrier_code"]),
                    bill_month=r.get("bill_month"),
                    tracking_no=str(r["tracking_no"]),
                    business_time=r.get("business_time"),
                    destination_province=r.get("destination_province"),
                    destination_city=r.get("destination_city"),
                    billing_weight_kg=_to_float(r.get("billing_weight_kg")),
                    freight_amount=_to_float(r.get("freight_amount")),
                    surcharge_amount=_to_float(r.get("surcharge_amount")),
                    total_amount=_to_float(r.get("total_amount")),
                    settlement_object=r.get("settlement_object"),
                    order_customer=r.get("order_customer"),
                    sender_name=r.get("sender_name"),
                    network_name=r.get("network_name"),
                    size_text=r.get("size_text"),
                    parent_customer=r.get("parent_customer"),
                    raw_payload=dict(r.get("raw_payload") or {}),
                    created_at=r["created_at"],
                )
                for r in rows
            ],
            total=total,
        )
