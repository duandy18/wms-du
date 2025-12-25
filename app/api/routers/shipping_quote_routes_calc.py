# app/api/routers/shipping_quote_routes_calc.py
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.services.shipping_quote_service import Dest, calc_quote

from app.api.routers.shipping_quote_helpers import check_perm, dims_from_payload
from app.api.routers.shipping_quote_schemas import QuoteCalcIn, QuoteCalcOut


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-quote/calc",
        response_model=QuoteCalcOut,
        status_code=status.HTTP_200_OK,
    )
    def calc_shipping_quote(
        payload: QuoteCalcIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        dims = dims_from_payload(payload.length_cm, payload.width_cm, payload.height_cm)

        try:
            result = calc_quote(
                db=db,
                scheme_id=payload.scheme_id,
                dest=Dest(
                    province=payload.dest.province,
                    city=payload.dest.city,
                    district=payload.dest.district,
                ),
                real_weight_kg=float(payload.real_weight_kg),
                dims_cm=dims,
                flags=payload.flags,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"calc failed: {e}")

        return QuoteCalcOut(
            ok=bool(result.get("ok", True)),
            quote_status=str(result.get("quote_status") or "OK"),
            currency=result.get("currency"),
            total_amount=result.get("total_amount"),
            weight=result.get("weight") or {},
            zone=result.get("zone"),
            bracket=result.get("bracket"),
            breakdown=result.get("breakdown") or {},
            reasons=result.get("reasons") or [],
        )
