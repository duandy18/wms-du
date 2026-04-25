# app/tms/shipment/routes_calc.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.core.error_detail import raise_422, raise_500
from app.db.deps import get_db
from app.tms.quote.recommend import recommend_quotes
from app.tms.quote.types import Dest

from .contracts_calc import (
    ShipCalcRequest,
    ShipCalcResponse,
    ShipQuoteOut,
    ShipRecommendedOut,
)


class ShipCalcErrorCode:
    INVALID = "SHIP_CALC_INVALID"
    FAILED = "SHIP_CALC_FAILED"


def register(router: APIRouter) -> None:
    @router.post("/shipping-assist/shipping/calc", response_model=ShipCalcResponse)
    async def calc_shipping_quotes(
        payload: ShipCalcRequest,
        db: Session = Depends(get_db),
        current_user: Any = Depends(get_current_user),
    ) -> ShipCalcResponse:
        _ = current_user

        try:
            raw = recommend_quotes(
                db=db,
                provider_ids=None,
                warehouse_id=int(payload.warehouse_id),
                dest=Dest(
                    province=payload.province,
                    city=payload.city,
                    district=payload.district,
                ),
                real_weight_kg=float(payload.weight_kg),
                dims_cm=None,
                flags=[],
                max_results=10,
            )
        except ValueError as e:
            raise_422(ShipCalcErrorCode.INVALID, str(e))
        except Exception as e:
            raise_500(ShipCalcErrorCode.FAILED, f"ship calc failed: {e}")

        quotes_raw = raw.get("quotes") or []
        quotes: list[ShipQuoteOut] = []
        for q in quotes_raw:
            quotes.append(
                ShipQuoteOut(
                    provider_id=int(q["provider_id"]),
                    carrier_code=q.get("carrier_code"),
                    carrier_name=str(q.get("carrier_name") or ""),
                    template_id=int(q["template_id"]),
                    template_name=q.get("template_name"),
                    quote_status=str(q.get("quote_status") or ""),
                    currency=q.get("currency"),
                    est_cost=float(q["total_amount"]) if q.get("total_amount") is not None else None,
                    reasons=list(q.get("reasons") or []),
                    breakdown=q.get("breakdown"),
                    eta=None,
                )
            )

        recommended: Optional[ShipRecommendedOut] = None
        if quotes:
            top = quotes[0]
            recommended = ShipRecommendedOut(
                provider_id=top.provider_id,
                carrier_code=top.carrier_code,
                template_id=top.template_id,
                est_cost=top.est_cost,
                currency=top.currency,
            )

        dest_str = None
        if payload.province or payload.city or payload.district:
            dest_str = "/".join([x for x in [payload.province, payload.city, payload.district] if x])

        return ShipCalcResponse(
            ok=bool(raw.get("ok", True)),
            weight_kg=float(payload.weight_kg),
            dest=dest_str,
            quotes=quotes,
            recommended=recommended,
        )
