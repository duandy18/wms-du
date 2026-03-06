# app/services/shipping_quote/calc_quote.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme

from .calc_core import check_scheme_warehouse_allowed, scheme_is_effective
from .calc_quote_level3 import calc_quote_level3
from .types import Dest, _utcnow

JsonObject = Dict[str, object]


def calc_quote(
    db: Session,
    scheme_id: int,
    warehouse_id: int,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise ValueError("scheme not found")

    now = _utcnow()
    if not scheme_is_effective(sch, now):
        raise ValueError("scheme not effective (inactive or out of date range)")

    check_scheme_warehouse_allowed(
        db,
        scheme_id=int(scheme_id),
        warehouse_id=int(warehouse_id),
    )

    return calc_quote_level3(
        db=db,
        sch=sch,
        dest=dest,
        real_weight_kg=real_weight_kg,
        dims_cm=dims_cm,
        flags=flags,
    )
