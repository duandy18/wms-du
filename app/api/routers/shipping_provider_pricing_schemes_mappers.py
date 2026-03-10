# app/api/routers/shipping_provider_pricing_schemes_mappers.py
from __future__ import annotations

from typing import List

from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    DestinationGroupOut,
    DestinationGroupProvinceOut,
    SchemeOut,
    SurchargeOut,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity


def to_destination_group_province_out(
    m: ShippingProviderDestinationGroupMember,
) -> DestinationGroupProvinceOut:
    return DestinationGroupProvinceOut(
        id=int(m.id),
        group_id=int(m.group_id),
        province_code=getattr(m, "province_code", None),
        province_name=getattr(m, "province_name", None),
    )


def to_destination_group_out(
    g: ShippingProviderDestinationGroup,
    provinces: List[ShippingProviderDestinationGroupMember],
    pricing_matrix: list[object] | None = None,
) -> DestinationGroupOut:
    return DestinationGroupOut(
        id=int(g.id),
        scheme_id=int(g.scheme_id),
        name=str(g.name),
        active=bool(g.active),
        provinces=[to_destination_group_province_out(x) for x in provinces],
    )


def _to_surcharge_out_from_config(
    cfg: ShippingProviderSurchargeConfig,
) -> SurchargeOut:
    return SurchargeOut(
        id=int(cfg.id),
        scheme_id=int(cfg.scheme_id),
        name=str(getattr(cfg, "province_name", None) or getattr(cfg, "province_code", None) or f"cfg#{cfg.id}"),
        active=bool(cfg.active),
        scope="province",
        province_code=getattr(cfg, "province_code", None),
        city_code=None,
        province_name=getattr(cfg, "province_name", None),
        city_name=None,
        fixed_amount=getattr(cfg, "fixed_amount", None),
    )


def _to_surcharge_out_from_city(
    cfg: ShippingProviderSurchargeConfig,
    city_row: ShippingProviderSurchargeConfigCity,
) -> SurchargeOut:
    return SurchargeOut(
        id=int(city_row.id),
        scheme_id=int(cfg.scheme_id),
        name=str(
            f"{getattr(cfg, 'province_name', None) or getattr(cfg, 'province_code', None)}-"
            f"{getattr(city_row, 'city_name', None) or getattr(city_row, 'city_code', None)}"
        ),
        active=bool(cfg.active) and bool(city_row.active),
        scope="city",
        province_code=getattr(cfg, "province_code", None),
        city_code=getattr(city_row, "city_code", None),
        province_name=getattr(cfg, "province_name", None),
        city_name=getattr(city_row, "city_name", None),
        fixed_amount=getattr(city_row, "fixed_amount", None),
    )


def to_surcharge_outs_from_config(
    cfg: ShippingProviderSurchargeConfig,
) -> List[SurchargeOut]:
    province_mode = str(getattr(cfg, "province_mode", "province") or "province").strip().lower()

    if province_mode == "province":
        return [_to_surcharge_out_from_config(cfg)]

    out: List[SurchargeOut] = []
    for city_row in getattr(cfg, "cities", []) or []:
        out.append(_to_surcharge_out_from_city(cfg, city_row))
    return out


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
        status=str(getattr(sch, "status", "draft")),
        archived_at=getattr(sch, "archived_at", None),
        currency=str(sch.currency),
        effective_from=getattr(sch, "effective_from", None),
        effective_to=getattr(sch, "effective_to", None),
        default_pricing_mode=str(dpm),
        billable_weight_strategy=str(getattr(sch, "billable_weight_strategy", "actual_only")),
        volume_divisor=getattr(sch, "volume_divisor", None),
        rounding_mode=str(getattr(sch, "rounding_mode", "none")),
        rounding_step_kg=(
            None if getattr(sch, "rounding_step_kg", None) is None else float(sch.rounding_step_kg)
        ),
        min_billable_weight_kg=(
            None if getattr(sch, "min_billable_weight_kg", None) is None else float(sch.min_billable_weight_kg)
        ),
        destination_groups=destination_groups or [],
        surcharges=surcharges or [],
    )
