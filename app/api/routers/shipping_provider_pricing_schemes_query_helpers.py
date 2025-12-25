# app/api/routers/shipping_provider_pricing_schemes_query_helpers.py
from __future__ import annotations

from typing import Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routers.shipping_provider_pricing_schemes_mappers import to_surcharge_out, to_zone_out
from app.api.routers.shipping_provider_pricing_schemes_schemas import SurchargeOut, ZoneOut
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def load_scheme_entities(
    db: Session,
    scheme_id: int,
) -> Tuple[ShippingProviderPricingScheme, List[ZoneOut], List[SurchargeOut]]:
    """
    读取 Scheme + Zones(+Members,+Brackets) + Surcharges，并组装为输出对象。
    - 只做查询与组装，不做权限校验
    - scheme 不存在则抛 404
    """
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    zones_raw = (
        db.query(ShippingProviderZone)
        .filter(ShippingProviderZone.scheme_id == scheme_id)
        .order_by(ShippingProviderZone.priority.asc(), ShippingProviderZone.id.asc())
        .all()
    )
    zone_ids = [z.id for z in zones_raw]

    members_by_zone: Dict[int, List[ShippingProviderZoneMember]] = {}
    brackets_by_zone: Dict[int, List[ShippingProviderZoneBracket]] = {}

    if zone_ids:
        members = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id.in_(zone_ids))
            .order_by(
                ShippingProviderZoneMember.zone_id.asc(),
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        for m in members:
            members_by_zone.setdefault(m.zone_id, []).append(m)

        brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id.in_(zone_ids))
            .order_by(
                ShippingProviderZoneBracket.zone_id.asc(),
                ShippingProviderZoneBracket.min_kg.asc(),
                ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
                ShippingProviderZoneBracket.id.asc(),
            )
            .all()
        )
        for b in brackets:
            brackets_by_zone.setdefault(b.zone_id, []).append(b)

    zones: List[ZoneOut] = []
    for z in zones_raw:
        zones.append(to_zone_out(z, members_by_zone.get(z.id, []), brackets_by_zone.get(z.id, [])))

    surcharges_raw = (
        db.query(ShippingProviderSurcharge)
        .filter(ShippingProviderSurcharge.scheme_id == scheme_id)
        .order_by(ShippingProviderSurcharge.priority.asc(), ShippingProviderSurcharge.id.asc())
        .all()
    )
    surcharges: List[SurchargeOut] = [to_surcharge_out(s) for s in surcharges_raw]

    return sch, zones, surcharges
