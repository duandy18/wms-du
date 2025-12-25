# app/api/routers/shipping_quote_routes_recommend.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.services.shipping_quote_service import Dest, recommend_quotes

from app.api.routers.shipping_quote_helpers import check_perm, dims_from_payload
from app.api.routers.shipping_quote_schemas import QuoteRecommendIn, QuoteRecommendOut


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

        try:
            result = recommend_quotes(
                db=db,
                provider_ids=payload.provider_ids or None,
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
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"recommend failed: {e}")

        return QuoteRecommendOut(
            ok=True,
            recommended_scheme_id=result.get("recommended_scheme_id"),
            quotes=result.get("quotes") or [],
        )
