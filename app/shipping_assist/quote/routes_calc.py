# app/shipping_assist/quote/routes_calc.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.core.error_detail import raise_422, raise_500
from app.db.deps import get_db
from app.wms.shared.services.audit_writer_sync import SyncAuditEventWriter
from app.shipping_assist.quote import Dest, calc_quote
from app.shipping_assist.quote_snapshot import build_quote_snapshot

from .contracts import QuoteCalcIn, QuoteCalcOut
from .error_codes import (
    QuoteCalcErrorCode,
    map_calc_value_error_to_code,
)
from .helpers import check_perm, dims_from_payload


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-assist/shipping/quote/calc",
        response_model=QuoteCalcOut,
        status_code=status.HTTP_200_OK,
    )
    def calc_shipping_quote(
        payload: QuoteCalcIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        dims = dims_from_payload(
            payload.length_cm,
            payload.width_cm,
            payload.height_cm,
        )

        audit_ref = f"WH:{int(payload.warehouse_id)}|TEMPLATE:{int(payload.template_id)}"

        try:
            result = calc_quote(
                db=db,
                template_id=payload.template_id,
                warehouse_id=payload.warehouse_id,
                dest=Dest(
                    province=payload.dest.province,
                    city=payload.dest.city,
                    district=payload.dest.district,
                    province_code=payload.dest.province_code,
                    city_code=payload.dest.city_code,
                ),
                real_weight_kg=float(payload.real_weight_kg),
                dims_cm=dims,
                flags=payload.flags,
            )
        except ValueError as e:
            msg = str(e)
            code = map_calc_value_error_to_code(msg)

            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_CALC_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-assist/shipping/quote/calc",
                    "error_code": code,
                    "message": msg,
                    "template_id": int(payload.template_id),
                    "warehouse_id": int(payload.warehouse_id),
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                },
                auto_commit=True,
            )

            raise_422(code, msg)

        except Exception as e:
            msg = f"calc failed: {e}"

            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_CALC_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-assist/shipping/quote/calc",
                    "error_code": QuoteCalcErrorCode.FAILED,
                    "message": msg,
                    "template_id": int(payload.template_id),
                    "warehouse_id": int(payload.warehouse_id),
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                },
                auto_commit=True,
            )

            raise_500(QuoteCalcErrorCode.FAILED, msg)

        quote_snapshot = build_quote_snapshot(
            source="shipping_quote.calc",
            input_payload=payload.model_dump(),
            selected_quote={
                "quote_status": str(result.get("quote_status") or "OK"),
                "template_id": int(payload.template_id),
                "template_name": None,
                "provider_id": result.get("shipping_provider_id"),
                "carrier_code": None,
                "carrier_name": None,
                "currency": result.get("currency"),
                "total_amount": result.get("total_amount"),
                "weight": result.get("weight") or {},
                "destination_group": result.get("destination_group"),
                "pricing_matrix": result.get("pricing_matrix"),
                "breakdown": result.get("breakdown") or {},
                "reasons": result.get("reasons") or [],
            },
        )

        return QuoteCalcOut(
            ok=bool(result.get("ok", True)),
            quote_status=str(result.get("quote_status") or "OK"),
            currency=result.get("currency"),
            total_amount=result.get("total_amount"),
            weight=result.get("weight") or {},
            destination_group=result.get("destination_group"),
            pricing_matrix=result.get("pricing_matrix"),
            breakdown=result.get("breakdown") or {},
            reasons=result.get("reasons") or [],
            quote_snapshot=quote_snapshot,
        )
