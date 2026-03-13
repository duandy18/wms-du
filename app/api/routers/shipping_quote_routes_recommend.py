# app/api/routers/shipping_quote_routes_recommend.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.error_detail import raise_422, raise_500
from app.db.deps import get_db
from app.services.audit_writer_sync import SyncAuditEventWriter
from app.services.shipping_quote_service import Dest, recommend_quotes

from app.api.routers.shipping_quote_helpers import check_perm, dims_from_payload
from app.api.routers.shipping_quote_schemas import QuoteRecommendItemOut, QuoteRecommendIn, QuoteRecommendOut
from app.tms.quote_snapshot import build_quote_snapshot


class QuoteRecommendErrorCode:
    INVALID = "QUOTE_RECOMMEND_INVALID"
    FAILED = "QUOTE_RECOMMEND_FAILED"


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-quote/recommend",
        response_model=QuoteRecommendOut,
        status_code=status.HTTP_200_OK,
    )
    def recommend_shipping_quote(
        payload: QuoteRecommendIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        dims = dims_from_payload(payload.length_cm, payload.width_cm, payload.height_cm)

        audit_ref = f"WH:{int(payload.warehouse_id)}"

        try:
            result = recommend_quotes(
                db=db,
                provider_ids=payload.provider_ids or None,
                warehouse_id=int(payload.warehouse_id),
                dest=Dest(
                    province=payload.dest.province,
                    city=payload.dest.city,
                    district=payload.dest.district,
                ),
                real_weight_kg=float(payload.real_weight_kg),
                dims_cm=dims,
                flags=payload.flags,
                max_results=int(payload.max_results),
            )
        except ValueError as e:
            msg = str(e)

            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_RECOMMEND_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-quote/recommend",
                    "error_code": QuoteRecommendErrorCode.INVALID,
                    "message": msg,
                    "warehouse_id": int(payload.warehouse_id),
                    "provider_ids": [int(x) for x in (payload.provider_ids or [])],
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                    "max_results": int(payload.max_results),
                },
                auto_commit=True,
            )

            raise_422(QuoteRecommendErrorCode.INVALID, msg)

        except Exception as e:
            msg = f"recommend failed: {e}"

            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_RECOMMEND_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-quote/recommend",
                    "error_code": QuoteRecommendErrorCode.FAILED,
                    "message": msg,
                    "warehouse_id": int(payload.warehouse_id),
                    "provider_ids": [int(x) for x in (payload.provider_ids or [])],
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                    "max_results": int(payload.max_results),
                },
                auto_commit=True,
            )

            raise_500(QuoteRecommendErrorCode.FAILED, msg)

        quote_items: list[QuoteRecommendItemOut] = []
        for item in result.get("quotes") or []:
            quote_snapshot = build_quote_snapshot(
                source="shipping_quote.recommend",
                input_payload=payload.model_dump(),
                selected_quote={
                    "provider_id": item.get("provider_id"),
                    "carrier_code": item.get("carrier_code"),
                    "carrier_name": item.get("carrier_name"),
                    "scheme_id": item.get("scheme_id"),
                    "scheme_name": item.get("scheme_name"),
                    "quote_status": item.get("quote_status"),
                    "currency": item.get("currency"),
                    "total_amount": item.get("total_amount"),
                    "weight": item.get("weight") or {},
                    "destination_group": item.get("destination_group"),
                    "pricing_matrix": item.get("pricing_matrix"),
                    "breakdown": item.get("breakdown") or {},
                    "reasons": item.get("reasons") or [],
                },
            )

            quote_items.append(
                QuoteRecommendItemOut(
                    provider_id=int(item["provider_id"]),
                    carrier_code=item.get("carrier_code"),
                    carrier_name=str(item.get("carrier_name") or ""),
                    scheme_id=int(item["scheme_id"]),
                    scheme_name=str(item.get("scheme_name") or ""),
                    total_amount=float(item["total_amount"]),
                    currency=item.get("currency"),
                    quote_status=str(item.get("quote_status") or "OK"),
                    weight=item.get("weight") or {},
                    destination_group=item.get("destination_group"),
                    pricing_matrix=item.get("pricing_matrix"),
                    breakdown=item.get("breakdown") or {},
                    reasons=item.get("reasons") or [],
                    quote_snapshot=quote_snapshot,
                )
            )

        return QuoteRecommendOut(
            ok=True,
            recommended_scheme_id=result.get("recommended_scheme_id"),
            quotes=quote_items,
        )
