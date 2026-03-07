# app/api/routers/shipping_provider_pricing_schemes_mappers.py
from __future__ import annotations

from typing import List

from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    DestinationGroupOut,
    DestinationGroupProvinceOut,
    PricingMatrixOut,
    SchemeOut,
    SurchargeOut,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def to_destination_group_province_out(
    m: ShippingProviderDestinationGroupMember,
) -> DestinationGroupProvinceOut:
    return DestinationGroupProvinceOut(
        id=int(m.id),
        group_id=int(m.group_id),
        province_code=getattr(m, "province_code", None),
        province_name=getattr(m, "province_name", None),
    )


def to_pricing_matrix_out(r: ShippingProviderPricingMatrix) -> PricingMatrixOut:
    return PricingMatrixOut(
        id=int(r.id),
        group_id=int(r.group_id),
        min_kg=r.min_kg,
        max_kg=r.max_kg,
        pricing_mode=str(r.pricing_mode),
        flat_amount=getattr(r, "flat_amount", None),
        base_amount=getattr(r, "base_amount", None),
        rate_per_kg=getattr(r, "rate_per_kg", None),
        base_kg=getattr(r, "base_kg", None),
        active=bool(r.active),
    )


def to_destination_group_out(
    g: ShippingProviderDestinationGroup,
    provinces: List[ShippingProviderDestinationGroupMember],
    pricing_matrix: List[ShippingProviderPricingMatrix],
) -> DestinationGroupOut:
    return DestinationGroupOut(
        id=int(g.id),
        scheme_id=int(g.scheme_id),
        name=str(g.name),
        active=bool(g.active),
        provinces=[to_destination_group_province_out(x) for x in provinces],
        pricing_matrix=[to_pricing_matrix_out(x) for x in pricing_matrix],
    )


def to_surcharge_out(s: ShippingProviderSurcharge) -> SurchargeOut:
    return SurchargeOut(
        id=int(s.id),
        scheme_id=int(s.scheme_id),
        name=str(s.name),
        active=bool(s.active),
        scope=str(getattr(s, "scope", "province") or "province"),
        province_code=getattr(s, "province_code", None),
        city_code=getattr(s, "city_code", None),
        province_name=getattr(s, "province_name", None),
        city_name=getattr(s, "city_name", None),
        fixed_amount=getattr(s, "fixed_amount", None),
    )


def _must_get_shipping_provider_name(sch: ShippingProviderPricingScheme) -> str:
    sp = getattr(sch, "shipping_provider", None)
    name = getattr(sp, "name", None) if sp is not None else None
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(
            f"ShippingProvider name is required for scheme_id={sch.id} "
            f"shipping_provider_id={sch.shipping_provider_id}"
        )
    return name.strip()


def to_scheme_out(
    sch: ShippingProviderPricingScheme,
    destination_groups: List[DestinationGroupOut] | None = None,
    surcharges: List[SurchargeOut] | None = None,
) -> SchemeOut:
    dpm = getattr(sch, "default_pricing_mode", "linear_total")

    return SchemeOut(
        id=int(sch.id),
        shipping_provider_id=int(sch.shipping_provider_id),
        shipping_provider_name=_must_get_shipping_provider_name(sch),
        name=str(sch.name),
        active=bool(sch.active),
        archived_at=getattr(sch, "archived_at", None),
        currency=str(sch.currency),
        effective_from=getattr(sch, "effective_from", None),
        effective_to=getattr(sch, "effective_to", None),
        default_pricing_mode=str(dpm),
        billable_weight_rule=getattr(sch, "billable_weight_rule", None),
        destination_groups=destination_groups or [],
        surcharges=surcharges or [],
    )
