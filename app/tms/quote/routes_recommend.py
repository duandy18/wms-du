# app/tms/quote/routes_recommend.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.quote import Dest
from app.tms.quote.contracts import QuoteRecommendIn, QuoteRecommendOut
from app.tms.quote.helpers import check_perm, dims_from_payload
from app.tms.quote.recommend import recommend_quotes


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-assist/shipping/quote/recommend",
        response_model=QuoteRecommendOut,
        status_code=status.HTTP_200_OK,
    )
    def recommend_shipping_quote(
        payload: QuoteRecommendIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        dims = dims_from_payload(
            payload.length_cm,
            payload.width_cm,
            payload.height_cm,
        )

        result = recommend_quotes(
            db=db,
            provider_ids=payload.provider_ids,
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
            max_results=int(payload.max_results),
        )

        return QuoteRecommendOut(
            ok=bool(result.get("ok", True)),
            recommended_template_id=result.get("recommended_template_id"),
            quotes=result.get("quotes") or [],
        )
